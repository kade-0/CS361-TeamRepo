const express = require("express");
const fs = require("fs");
const https = require("https");
const store = require("./db");
const { rateLimit } = require("./ratelimit");
const { log, maskEmail, requestLogger } = require("./logger");

const PORT = process.env.PORT || 4000;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const EMAIL_MAX = 254;
const MIN_PASSWORD_LENGTH = 12;
const MAX_PASSWORD_LENGTH = 256;
const DISPLAY_NAME_MAX = 40;
const REGISTERED_MESSAGE = "Thanks! Check your email for a link to verify your account.";

// account response shape function

function accountView(account) {
  return { id: account.id, email: account.email, displayName: account.display_name, status: account.status, createdAt: account.created_at };
}

// bearer token authentication function

function requireAuth(req, res, next) {
  const [scheme, token] = (req.get("Authorization") || "").split(" ");
  const account = scheme === "Bearer" && token && store.findAccountByToken(token);
  if (!account) {
    log(req, "auth.rejected", { reason: token ? "invalid_token" : "missing_token" });
    return res.status(401).json({ error: "Missing or invalid access token." });
  }
  req.account = account;
  req.token = token;
  next();
}

// registration validation functions, each returns a message for its field or null

function validateEmail(email) {
  if (typeof email !== "string" || !email.trim()) return "Email is required.";
  if (email.trim().length > EMAIL_MAX) return `Email must be ${EMAIL_MAX} characters or less.`;
  if (!EMAIL_RE.test(email.trim())) return "Enter a valid email address, like name@example.com.";
  return null;
}

function validatePassword(password) {
  if (typeof password !== "string" || !password) return "Password is required.";
  if (password.length < MIN_PASSWORD_LENGTH) return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  if (password.length > MAX_PASSWORD_LENGTH) return `Password must be ${MAX_PASSWORD_LENGTH} characters or less.`;
  return null;
}

function validateDisplayName(displayName) {
  if (typeof displayName !== "string" || !displayName.trim()) return "Display name is required.";
  if (displayName.trim().length > DISPLAY_NAME_MAX) return `Display name must be ${DISPLAY_NAME_MAX} characters or less.`;
  return null;
}

function validateRegistration({ email, password, displayName }) {
  const fields = {};
  const checks = { email: validateEmail(email), password: validatePassword(password), displayName: validateDisplayName(displayName) };
  Object.entries(checks).forEach(([field, message]) => { if (message) fields[field] = message; });
  return Object.keys(fields).length ? fields : null;
}

// registration handler function; the response never says whether the email was already taken

async function handleRegister(req, res) {
  const fields = validateRegistration(req.body || {});
  if (fields) {
    log(req, "register.rejected", { fields: Object.keys(fields).join(",") });
    return res.status(400).json({ error: "Please fix the highlighted fields.", fields });
  }
  const result = await store.registerAccount(req.body.email.trim(), req.body.password, req.body.displayName.trim());
  log(req, result.created ? "account.created" : "register.email_taken", { account: result.accountId, email: maskEmail(req.body.email) });
  log(req, "email.queued", { template: result.template, account: result.accountId });
  res.status(202).json({ message: REGISTERED_MESSAGE });
}

// login and logout handler functions

async function handleLogin(req, res) {
  const { email, password } = req.body || {};
  const account = typeof email === "string" && store.findAccountByEmail(email.trim());
  if (!account || typeof password !== "string" || !(await store.verifyPassword(password, account.password_hash))) {
    log(req, "login.failed", { email: maskEmail(email), reason: account ? "wrong_password" : "unknown_email" });
    return res.status(401).json({ error: "Incorrect email or password." });
  }
  const { token, expiresAt } = store.issueAccessToken(account.id);
  log(req, "login.success", { account: account.id });
  res.json({ accessToken: token, tokenType: "Bearer", expiresAt, account: accountView(account) });
}

function handleLogout(req, res) {
  store.revokeAccessToken(req.token);
  log(req, "logout", { account: req.account.id });
  res.status(204).end();
}

// current account handler function

function handleMe(req, res) {
  log(req, "account.viewed", { account: req.account.id });
  res.json(accountView(req.account));
}

// passes rejected promises from async handlers to the error handler

function wrap(handler) {
  return (req, res, next) => Promise.resolve(handler(req, res, next)).catch(next);
}

// placeholder for endpoints that are part of the API but they aren't in quite yet

function notImplemented(req, res) {
  res.status(501).json({ error: "Not implemented yet." });
}

function setupRoutes(app) {
  // for rate limiting to work correctly behind a reverse proxy, we need to trust the proxy (e.g. Cloudflare).
  app.set("trust proxy", process.env.TRUST_PROXY || "loopback");
  
  app.use(requestLogger);
  app.use(express.json({ limit: "10kb" }));
  app.post("/v1/accounts", rateLimit({ windowMs: 60 * 1000, max: 5 }), wrap(handleRegister));
  app.post("/v1/accounts/verify-email", notImplemented);
  app.post("/v1/accounts/verify-email/resend", notImplemented);
  app.get("/v1/accounts/me", requireAuth, handleMe);
  app.patch("/v1/accounts/me", requireAuth, notImplemented);
  app.delete("/v1/accounts/me", requireAuth, notImplemented);
  app.post("/v1/auth/login", wrap(handleLogin));
  app.post("/v1/auth/logout", requireAuth, handleLogout);
  app.post("/v1/auth/password-reset/request", notImplemented);
  app.post("/v1/auth/password-reset/confirm", notImplemented);
  app.use((req, res) => res.status(404).json({ error: "Not found." }));
  app.use((err, req, res, next) => {
    if (err.type === "entity.parse.failed") {
      log(req, "request.bad_json", { path: req.path });
      return res.status(400).json({ error: "Request body must be valid JSON." });
    }
    // log only the error itself, never the request body (it may hold a password)
    log(req, "error", { path: req.path, message: JSON.stringify(err.message) });
    console.error(err.stack || err.message);
    res.status(500).json({ error: "Something went wrong. Try again." });
  });
}

function startServer() {
  const app = express();
  setupRoutes(app);
  setInterval(store.clearExpiredTokens, 15 * 60 * 1000).unref();
  listen(app);
}

function listen(app) {
  const { TLS_KEY_PATH, TLS_CERT_PATH } = process.env;
  if (!TLS_KEY_PATH || !TLS_CERT_PATH) {
    return app.listen(PORT, () => console.log(`Account service running at http://localhost:${PORT}`));
  }
  const options = { key: fs.readFileSync(TLS_KEY_PATH), cert: fs.readFileSync(TLS_CERT_PATH), minVersion: "TLSv1.2" };
  https.createServer(options, app).listen(PORT, () => console.log(`Account service running at https://localhost:${PORT}`));
}

startServer();
