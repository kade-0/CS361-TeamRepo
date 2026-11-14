const Database = require("better-sqlite3");
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
  // access tokens are stored only as a sha256 hash so a leaked database cannot be replayed
  db.exec(`
    CREATE TABLE IF NOT EXISTS access_tokens (
      token_hash TEXT PRIMARY KEY,
      account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      expires_at TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);
}

// simple password hashing and verification functions

function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString("hex");
  const hash = crypto.scryptSync(password, salt, 64).toString("hex");
  return `${salt}:${hash}`;
}

function verifyPassword(password, stored) {
  const [salt, hash] = stored.split(":");
  const test = crypto.scryptSync(password, salt, 64);
  return crypto.timingSafeEqual(test, Buffer.from(hash, "hex"));
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

// account creation function

function createAccount(email, password, displayName) {
  const id = crypto.randomUUID();
  db.prepare("INSERT INTO accounts (id, email, display_name, password_hash) VALUES (?, ?, ?, ?)").run(id, email, displayName, hashPassword(password));
  return id;
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

module.exports = { db, verifyPassword, findAccountByEmail, findAccountById, createAccount, issueAccessToken, findAccountByToken, revokeAccessToken, clearExpiredTokens };
