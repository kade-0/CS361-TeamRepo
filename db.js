const Database = require("better-sqlite3");
const argon2 = require("argon2");
const path = require("path");
const crypto = require("crypto");

const DB_PATH = process.env.ACCOUNTS_DB_PATH || path.join(__dirname, "accounts.db");
const TOKEN_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const VERIFY_TOKEN_TTL_MS = 24 * 60 * 60 * 1000;

const db = new Database(DB_PATH);
db.pragma("journal_mode = WAL");
db.pragma("foreign_keys = ON");

// Create the initial schema for the accounts database.

function initSchema() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS accounts (
      id TEXT PRIMARY KEY,
      email TEXT NOT NULL UNIQUE COLLATE NOCASE,
      display_name TEXT NOT NULL,
      password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);
  addColumnIfMissing("accounts", "status", "TEXT NOT NULL DEFAULT 'pending_verification'");
  db.exec(`
    CREATE TABLE IF NOT EXISTS access_tokens (
      token_hash TEXT PRIMARY KEY,
      account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      expires_at TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);
  db.exec(`
    CREATE TABLE IF NOT EXISTS email_outbox (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      template TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'queued',
      attempts INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      sent_at TEXT
    )
  `);
  addColumnIfMissing("email_outbox", "next_attempt_at", "TEXT");
  addColumnIfMissing("email_outbox", "last_error", "TEXT");
  db.exec(`
    CREATE TABLE IF NOT EXISTS verification_tokens (
      token_hash TEXT PRIMARY KEY,
      account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      expires_at TEXT NOT NULL,
      used_at TEXT,
      invalidated_at TEXT,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);
  db.exec("CREATE INDEX IF NOT EXISTS verification_tokens_account ON verification_tokens (account_id)");
}
function addColumnIfMissing(table, column, type) {
  const columns = db.prepare(`PRAGMA table_info(${table})`).all();
  if (!columns.some(c => c.name === column)) db.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${type}`);
}

// password hashing and verification functions (Argon2id, run off the main thread)

function hashPassword(password) {
  return argon2.hash(password, { type: argon2.argon2id });
}

async function verifyPassword(password, stored) {
  try {
    return await argon2.verify(stored, password);
  } catch {
    return false;
  }
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function now() {
  return new Date().toISOString();
}

// account query functions

function findAccountByEmail(email) {
  return db.prepare("SELECT * FROM accounts WHERE email = ?").get(email);
}

function findAccountById(id) {
  return db.prepare("SELECT * FROM accounts WHERE id = ?").get(id);
}

function queueEmail(accountId, template) {
  db.prepare("INSERT INTO email_outbox (account_id, template) VALUES (?, ?)").run(accountId, template);
}

const registerTx = db.transaction((email, passwordHash, displayName) => {
  const existing = findAccountByEmail(email);
  if (existing) {
    queueEmail(existing.id, "account_exists");
    return { accountId: existing.id, created: false, template: "account_exists" };
  }
  const id = crypto.randomUUID();
  db.prepare("INSERT INTO accounts (id, email, display_name, password_hash) VALUES (?, ?, ?, ?)").run(id, email, displayName, passwordHash);
  queueEmail(id, "verify_email");
  return { accountId: id, created: true, template: "verify_email" };
});

async function registerAccount(email, password, displayName) {
  const passwordHash = await hashPassword(password);
  return registerTx(email, passwordHash, displayName);
}

// email verification functions

function invalidateVerificationTokens(accountId) {
  db.prepare("UPDATE verification_tokens SET invalidated_at = ? WHERE account_id = ? AND used_at IS NULL AND invalidated_at IS NULL").run(now(), accountId);
}

const createVerificationToken = db.transaction(accountId => {
  invalidateVerificationTokens(accountId);
  const token = crypto.randomBytes(32).toString("base64url");
  const expiresAt = new Date(Date.now() + VERIFY_TOKEN_TTL_MS).toISOString();
  db.prepare("INSERT INTO verification_tokens (token_hash, account_id, expires_at) VALUES (?, ?, ?)").run(sha256(token), accountId, expiresAt);
  return token;
});

const verifyEmailToken = db.transaction(token => {
  const row = db.prepare("SELECT * FROM verification_tokens WHERE token_hash = ?").get(sha256(token));
  if (!row) return { outcome: "invalid" };
  const result = { accountId: row.account_id };
  if (row.used_at) return { ...result, outcome: "used" };
  if (row.invalidated_at) return { ...result, outcome: "superseded" };
  if (row.expires_at <= now()) return { ...result, outcome: "expired" };
  db.prepare("UPDATE verification_tokens SET used_at = ? WHERE token_hash = ?").run(now(), row.token_hash);
  db.prepare("UPDATE accounts SET status = 'active', updated_at = datetime('now') WHERE id = ? AND status = 'pending_verification'").run(row.account_id);
  return { ...result, outcome: "verified" };
});

const requestVerificationResend = db.transaction(email => {
  const account = findAccountByEmail(email);
  if (!account) return { outcome: "no_account" };
  if (account.status !== "pending_verification") return { outcome: "already_active", accountId: account.id };
  invalidateVerificationTokens(account.id);
  queueEmail(account.id, "verify_email");
  return { outcome: "queued", accountId: account.id };
});

// email outbox functions, used by the email worker

const claimDueEmails = db.transaction(limit => {
  const jobs = db.prepare(`
    SELECT email_outbox.*, accounts.email, accounts.display_name, accounts.status AS account_status
    FROM email_outbox JOIN accounts ON accounts.id = email_outbox.account_id
    WHERE email_outbox.status = 'queued' AND (email_outbox.next_attempt_at IS NULL OR email_outbox.next_attempt_at <= ?)
    ORDER BY email_outbox.id LIMIT ?
  `).all(now(), limit);
  const claim = db.prepare("UPDATE email_outbox SET status = 'sending' WHERE id = ?");
  jobs.forEach(job => claim.run(job.id));
  return jobs;
});

function markEmailSent(id) {
  db.prepare("UPDATE email_outbox SET status = 'sent', sent_at = ?, attempts = attempts + 1, last_error = NULL WHERE id = ?").run(now(), id);
}

function markEmailSkipped(id) {
  db.prepare("UPDATE email_outbox SET status = 'skipped' WHERE id = ?").run(id);
}

function markEmailRetry(id, nextAttemptAt, error) {
  db.prepare("UPDATE email_outbox SET status = 'queued', attempts = attempts + 1, next_attempt_at = ?, last_error = ? WHERE id = ?").run(nextAttemptAt, error, id);
}

function markEmailFailed(id, error) {
  db.prepare("UPDATE email_outbox SET status = 'failed', attempts = attempts + 1, last_error = ? WHERE id = ?").run(error, id);
}

function requeueStuckEmails() {
  return db.prepare("UPDATE email_outbox SET status = 'queued' WHERE status = 'sending'").run().changes;
}

// access token functions

function issueAccessToken(accountId) {
  const token = crypto.randomBytes(32).toString("base64url");
  const expiresAt = new Date(Date.now() + TOKEN_TTL_MS).toISOString();
  db.prepare("INSERT INTO access_tokens (token_hash, account_id, expires_at) VALUES (?, ?, ?)").run(sha256(token), accountId, expiresAt);
  return { token, expiresAt };
}

function findAccountByToken(token) {
  return db.prepare(`
    SELECT accounts.* FROM access_tokens
    JOIN accounts ON accounts.id = access_tokens.account_id
    WHERE access_tokens.token_hash = ? AND access_tokens.expires_at > ?
  `).get(sha256(token), new Date().toISOString());
}

function revokeAccessToken(token) {
  db.prepare("DELETE FROM access_tokens WHERE token_hash = ?").run(sha256(token));
}

function clearExpiredTokens() {
  db.prepare("DELETE FROM access_tokens WHERE expires_at <= ?").run(new Date().toISOString());
}

initSchema();

module.exports = {
  db, verifyPassword, findAccountByEmail, findAccountById, registerAccount,
  createVerificationToken, verifyEmailToken, requestVerificationResend,
  claimDueEmails, markEmailSent, markEmailSkipped, markEmailRetry, markEmailFailed, requeueStuckEmails,
  issueAccessToken, findAccountByToken, revokeAccessToken, clearExpiredTokens
};
