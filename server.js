const express = require("express");
const fs = require("fs");
const https = require("https");
const store = require("./db");
const { rateLimit } = require("./ratelimit");
const { log, maskEmail, requestLogger } = require("./logger");
const emailWorker = require("./emailworker");

const PORT = process.env.PORT || 4000;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const EMAIL_MAX = 254;
const MIN_PASSWORD_LENGTH = 12;
const MAX_PASSWORD_LENGTH = 256;
const DISPLAY_NAME_MAX = 40;
const REGISTERED_MESSAGE = "Thanks! Check your email for a link to verify your account.";
const RESEND_MESSAGE = "If that email belongs to an account that still needs verifying, we've sent it a new link.";
const NOT_VERIFIED = { error: "Please verify your email before logging in. Check your inbox for the link, or request a new one.", code: "email_not_verified" };

// what the verify endpoint says for each way a token can be rejected
const TOKEN_ERRORS = {
  invalid: { error: "This verification link is not valid. Request a new one below.", code: "token_invalid" },
  superseded: { error: "This verification link was replaced by a newer one. Use the newest email, or request a new link below.", code: "token_invalid" },
  used: { error: "This verification link has already been used. If your email is verified, you can log in.", code: "token_used" },
  expired: { error: "This verification link has expired. Request a new one below.", code: "token_expired" }
};

const RESET_REQUESTED_MESSAGE = "If that email belongs to an account, we've sent it a link to reset your password. The link expires in 30 minutes.";
const PASSWORD_CHANGED_MESSAGE = "Your password has been changed and you've been logged out everywhere. Log in with your new password.";
const RECENT_PASSWORD = { error: "You've used that password recently. Choose a password that isn't one of your last 5.", code: "password_recently_used" };

// what the password reset endpoints say for each way a reset link can be rejected
const RESET_TOKEN_ERRORS = {
  invalid: { error: "This password reset link is not valid. Request a new one below.", code: "token_invalid" },
  superseded: { error: "This password reset link was replaced by a newer one. Use the newest email, or request a new link below.", code: "token_invalid" },
  used: { error: "This password reset link has already been used. Request a new one below if you still need to reset your password.", code: "token_used" },
  expired: { error: "This password reset link has expired. Links only work for 30 minutes. Request a new one below.", code: "token_expired" }
};

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
  if (account.status !== "active") {
    log(req, "auth.rejected", { reason: "email_not_verified", account: account.id });
    return res.status(403).json(NOT_VERIFIED);
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
  emailWorker.kick();
  res.status(202).json({ message: REGISTERED_MESSAGE });
}

// email verification handler functions; outcomes are logged for auditing, tokens never are

function handleVerifyEmail(req, res) {
  const token = req.body && req.body.token;
  if (typeof token !== "string" || !token) {
    log(req, "verify.rejected", { outcome: "missing_token" });
    return res.status(400).json(TOKEN_ERRORS.invalid);
  }
  const result = store.verifyEmailToken(token);
  if (result.outcome !== "verified") {
    log(req, "verify.rejected", { outcome: result.outcome, account: result.accountId || "-" });
    return res.status(400).json(TOKEN_ERRORS[result.outcome]);
  }
  log(req, "verify.succeeded", { account: result.accountId });
  res.json({ message: "Your email is verified. You can now log in.", status: "active" });
}

// the response is identical whether the email is unknown, pending or already verified

function handleResendVerification(req, res) {
  const email = req.body && req.body.email;
  const error = validateEmail(email);
  if (error) return res.status(400).json({ error: "Please fix the highlighted fields.", fields: { email: error } });
  const result = store.requestVerificationResend(email.trim());
  log(req, "verify.resend", { outcome: result.outcome, account: result.accountId || "-", email: maskEmail(email) });
  if (result.outcome === "queued") {
    log(req, "email.queued", { template: "verify_email", account: result.accountId });
    emailWorker.kick();
  }
  res.status(202).json({ message: RESEND_MESSAGE });
}

// rate limit key for limiting per account (by email address) rather than per IP

function emailKey(req) {
  const email = req.body && req.body.email;
  return typeof email === "string" ? email.trim().toLowerCase() : req.ip;
}

// login and logout handler functions

async function handleLogin(req, res) {
  const { email, password } = req.body || {};
  const account = typeof email === "string" && store.findAccountByEmail(email.trim());
  if (!account || typeof password !== "string" || !(await store.verifyPassword(password, account.password_hash))) {
    log(req, "login.failed", { email: maskEmail(email), reason: account ? "wrong_password" : "unknown_email" });
    return res.status(401).json({ error: "Incorrect email or password." });
  }
  // only checked after the password, so account status is never revealed to someone without it
  if (account.status !== "active") {
    log(req, "login.denied", { account: account.id, reason: "email_not_verified" });
    return res.status(403).json(NOT_VERIFIED);
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

// password reset handler functions; outcomes are logged for auditing, tokens and passwords never are

function handlePasswordResetRequest(req, res) {
  const email = req.body && req.body.email;
  const error = validateEmail(email);
  if (error) return res.status(400).json({ error: "Please fix the highlighted fields.", fields: { email: error } });
  // respond before looking the email up, so known and unknown emails take the same time to answer
  res.status(202).json({ message: RESET_REQUESTED_MESSAGE });
  setImmediate(() => queuePasswordReset(req, email.trim()));
}

function queuePasswordReset(req, email) {
  try {
    const result = store.requestPasswordReset(email);
    log(req, "password_reset.requested", { outcome: result.outcome, account: result.accountId || "-", email: maskEmail(email) });
    if (result.outcome === "queued") {
      log(req, "email.queued", { template: "password_reset", account: result.accountId });
      emailWorker.kick();
    }
  } catch (err) {
    logError(req, err);
  }
}

function findResetToken(req) {
  const token = req.body && req.body.token;
  if (typeof token !== "string" || !token) return { outcome: "invalid" };
  return store.checkPasswordResetToken(token);
}

function rejectResetToken(req, res, result) {
  log(req, "password_reset.rejected", { outcome: result.outcome, account: result.accountId || "-" });
  res.status(400).json(RESET_TOKEN_ERRORS[result.outcome]);
}

// lets the reset page check its link as soon as it opens, before the user types a new password

function handlePasswordResetCheck(req, res) {
  const result = findResetToken(req);
  if (result.outcome !== "valid") return rejectResetToken(req, res, result);
  res.json({ message: "This link is valid. Choose a new password." });
}

async function handlePasswordResetConfirm(req, res) {
  const tokenCheck = findResetToken(req);
  if (tokenCheck.outcome !== "valid") return rejectResetToken(req, res, tokenCheck);

  const { token, newPassword } = req.body;
  const policyError = validatePassword(newPassword);
  if (policyError) {
    log(req, "password_reset.rejected", { outcome: "password_policy", account: tokenCheck.accountId });
    return res.status(400).json({ error: "Please fix the highlighted fields.", fields: { newPassword: policyError } });
  }
  if (await store.isRecentPassword(tokenCheck.accountId, newPassword)) {
    log(req, "password_reset.rejected", { outcome: "password_recently_used", account: tokenCheck.accountId });
    return res.status(400).json({ ...RECENT_PASSWORD, fields: { newPassword: RECENT_PASSWORD.error } });
  }

  const result = await store.resetPassword(token, newPassword);
  if (result.outcome !== "reset") return rejectResetToken(req, res, result);
  log(req, "password_reset.completed", { account: result.accountId, sessions_revoked: result.sessionsRevoked });
  log(req, "email.queued", { template: "password_changed", account: result.accountId });
  emailWorker.kick();
  res.json({ message: PASSWORD_CHANGED_MESSAGE });
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

// log only the error itself, never the request body (it may hold a password)

function logError(req, err) {
  log(req, "error", { path: req.path, message: JSON.stringify(err.message) });
  console.error(err.stack || err.message);
}

// placeholder for endpoints that are part of the API but they aren't in quite yet

function notImplemented(req, res) {
  res.status(501).json({ error: "Not implemented yet." });
}

function setupRoutes(app) {
  // for rate limiting to work correctly behind a reverse proxy, we need to trust the proxy (e.g. Cloudflare).
  app.set("trust proxy", process.env.TRUST_PROXY || "loopback");
  
  // one limit shared by checking and using reset links
  const resetLinkLimit = rateLimit({ windowMs: 15 * 60 * 1000, max: 20 });

  app.use(requestLogger);
  app.use(express.json({ limit: "10kb" }));
  app.post("/v1/accounts", rateLimit({ windowMs: 60 * 1000, max: 5 }), wrap(handleRegister));
  app.post("/v1/accounts/verify-email", handleVerifyEmail);
  app.post("/v1/accounts/verify-email/resend", rateLimit({ windowMs: 60 * 60 * 1000, max: 3, key: emailKey }), handleResendVerification);
  app.get("/v1/accounts/me", requireAuth, handleMe);
  app.patch("/v1/accounts/me", requireAuth, notImplemented);
  app.delete("/v1/accounts/me", requireAuth, notImplemented);
  app.post("/v1/auth/login", wrap(handleLogin));
  app.post("/v1/auth/logout", requireAuth, handleLogout);
  app.post("/v1/auth/password-reset/request",
    rateLimit({ windowMs: 15 * 60 * 1000, max: 10 }),
    rateLimit({ windowMs: 60 * 60 * 1000, max: 3, key: emailKey }),
    handlePasswordResetRequest);
  app.post("/v1/auth/password-reset/check", resetLinkLimit, handlePasswordResetCheck);
  app.post("/v1/auth/password-reset/confirm", resetLinkLimit, wrap(handlePasswordResetConfirm));
  app.use((req, res) => res.status(404).json({ error: "Not found." }));
  app.use((err, req, res, next) => {
    if (err.type === "entity.parse.failed") {
      log(req, "request.bad_json", { path: req.path });
      return res.status(400).json({ error: "Request body must be valid JSON." });
    }
    logError(req, err);
    res.status(500).json({ error: "Something went wrong. Try again." });
  });
}

function startServer() {
  const app = express();
  setupRoutes(app);
  setInterval(store.clearExpiredTokens, 15 * 60 * 1000).unref();
  emailWorker.start();
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
