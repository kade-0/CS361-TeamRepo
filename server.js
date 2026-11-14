const express = require("express");
const store = require("./db");

const PORT = process.env.PORT || 4000;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD_LENGTH = 8;
const DISPLAY_NAME_MAX = 40;

// account response shape function

function accountView(account) {
  return { id: account.id, email: account.email, displayName: account.display_name, createdAt: account.created_at };
}

// bearer token authentication function

function requireAuth(req, res, next) {
  const [scheme, token] = (req.get("Authorization") || "").split(" ");
  const account = scheme === "Bearer" && token && store.findAccountByToken(token);
  if (!account) return res.status(401).json({ error: "Missing or invalid access token." });
  req.account = account;
  req.token = token;
  next();
}

// registration validation function

function validateRegistration({ email, password, displayName }) {
  if (!displayName || !displayName.trim()) return "Display name is required.";
  if (displayName.trim().length > DISPLAY_NAME_MAX) return `Display name must be ${DISPLAY_NAME_MAX} characters or less.`;
  if (!email || !EMAIL_RE.test(email)) return "Enter a valid email address.";
  if (!password || password.length < MIN_PASSWORD_LENGTH) return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  if (store.findAccountByEmail(email.trim())) return "An account with this email already exists.";
  return null;
}

// registration handler function

function handleRegister(req, res) {
  const error = validateRegistration(req.body);
  if (error) return res.status(400).json({ error });
  const id = store.createAccount(req.body.email.trim(), req.body.password, req.body.displayName.trim());
  res.status(201).json(accountView(store.findAccountById(id)));
}

// login and logout handler functions

function handleLogin(req, res) {
  const { email, password } = req.body;
  const account = email && store.findAccountByEmail(email.trim());
  if (!account || !password || !store.verifyPassword(password, account.password_hash)) {
    return res.status(401).json({ error: "Incorrect email or password." });
  }
  const { token, expiresAt } = store.issueAccessToken(account.id);
  res.json({ accessToken: token, tokenType: "Bearer", expiresAt, account: accountView(account) });
}

function handleLogout(req, res) {
  store.revokeAccessToken(req.token);
  res.status(204).end();
}

// current account handler function

function handleMe(req, res) {
  res.json(accountView(req.account));
}

// placeholder for endpoints that are part of the API but they aren't in quite yet

function notImplemented(req, res) {
  res.status(501).json({ error: "Not implemented yet." });
}

function setupRoutes(app) {
  app.use(express.json());
  app.post("/v1/accounts", handleRegister);
  app.post("/v1/accounts/verify-email", notImplemented);
  app.post("/v1/accounts/verify-email/resend", notImplemented);
  app.get("/v1/accounts/me", requireAuth, handleMe);
  app.patch("/v1/accounts/me", requireAuth, notImplemented);
  app.delete("/v1/accounts/me", requireAuth, notImplemented);
  app.post("/v1/auth/login", handleLogin);
  app.post("/v1/auth/logout", requireAuth, handleLogout);
  app.post("/v1/auth/password-reset/request", notImplemented);
  app.post("/v1/auth/password-reset/confirm", notImplemented);
  app.use((req, res) => res.status(404).json({ error: "Not found." }));
  app.use((err, req, res, next) => {
    if (err.type === "entity.parse.failed") return res.status(400).json({ error: "Request body must be valid JSON." });
    console.error(err);
    res.status(500).json({ error: "Something went wrong. Try again." });
  });
}

function startServer() {
  const app = express();
  setupRoutes(app);
  setInterval(store.clearExpiredTokens, 15 * 60 * 1000).unref();
  app.listen(PORT, () => console.log(`Account service running at http://localhost:${PORT}`));
}

startServer();
