const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const nodemailer = require("nodemailer");

const MAIL_FROM = process.env.MAIL_FROM || "Multiplayer Service <no-reply@localhost>";
const MAIL_DIR = process.env.MAIL_DIR || path.join(__dirname, "mail");

// sends through SMTP when SMTP_HOST is set, otherwise writes each email to MAIL_DIR as a json file.

const transport = process.env.SMTP_HOST
  ? nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port: Number(process.env.SMTP_PORT || 587),
      secure: process.env.SMTP_SECURE === "true",
      auth: process.env.SMTP_USER ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS } : undefined,
      requireTLS: process.env.SMTP_SECURE !== "true",
      tls: { minVersion: "TLSv1.2" }
    })
  : null;

function describe() {
  return transport ? `SMTP ${process.env.SMTP_HOST}` : `dev inbox ${MAIL_DIR}`;
}

async function deliver(message) {
  if (transport) return transport.sendMail({ from: MAIL_FROM, ...message });
  fs.mkdirSync(MAIL_DIR, { recursive: true });
  const file = path.join(MAIL_DIR, `${Date.now()}-${crypto.randomUUID()}.json`);
  fs.writeFileSync(file, JSON.stringify({ from: MAIL_FROM, ...message, sentAt: new Date().toISOString() }, null, 2));
}

module.exports = { deliver, describe };
