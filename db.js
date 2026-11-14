const Database = require("better-sqlite3");
const argon2 = require("argon2");
const path = require("path");
const crypto = require("crypto");

const DB_PATH = process.env.ACCOUNTS_DB_PATH || path.join(__dirname, "accounts.db");
const TOKEN_TTL_MS = 7 * 24 * 60 * 60 * 1000;

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
  // access tokens are stored only as a sha256 hash so a leaked database cannot be replayed
  db.exec(`
    CREATE TABLE IF NOT EXISTS access_tokens (
      token_hash TEXT PRIMARY KEY,
      account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      expires_at TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);
  // emails waiting to be sent; rows are written in the same transaction as the change that caused them
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
}

// adds a column to an existing table so older databases keep working

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

// registration: creates a pending account and queues its verification email in one transaction.
// if the email is taken, the owner is sent a notice instead, so the caller sees the same result either way.

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
  // always hash first so taken and new emails take the same time
  const passwordHash = await hashPassword(password);
  return registerTx(email, passwordHash, displayName);
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

module.exports = { db, verifyPassword, findAccountByEmail, findAccountById, registerAccount, issueAccessToken, findAccountByToken, revokeAccessToken, clearExpiredTokens };
