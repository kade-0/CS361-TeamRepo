const store = require("./db");
const mailer = require("./mailer");
const { log } = require("./logger");

const VERIFY_URL = process.env.VERIFY_URL || "http://localhost:3000/verify-email";
const POLL_MS = 2000;
const BATCH_SIZE = 10;
const MAX_ATTEMPTS = 8;
const BASE_BACKOFF_MS = 5000;
const MAX_BACKOFF_MS = 15 * 60 * 1000;

let running = false;

// email templates; returns null when the email no longer needs sending

function buildMessage(job) {
  if (job.template === "verify_email") {
    if (job.account_status !== "pending_verification") return null;

    const token = store.createVerificationToken(job.account_id);
    const link = `${VERIFY_URL}#token=${token}`;
    return {
      to: job.email,
      subject: "Verify your email address",
      text: `Hi ${job.display_name},\n\nConfirm your email address to activate your account:\n\n${link}\n\nThis link expires in 24 hours and can only be used once. If you didn't create an account, you can ignore this email.\n`
    };
  }
  if (job.template === "account_exists") {
    return {
      to: job.email,
      subject: "Someone tried to sign up with your email",
      text: `Hi ${job.display_name},\n\nSomeone tried to create a account with this email address, but you already have one. If it was you, just log in.\n\nIf it wasn't you, you can ignore this email. Your account has not been changed.\n`
    };
  }
  throw new Error(`Unknown email template: ${job.template}`);
}

// waits 5s, 10s, 20s ... between attempts, capped at 15 minutes

function backoffMs(attempt) {
  return Math.min(BASE_BACKOFF_MS * 2 ** (attempt - 1), MAX_BACKOFF_MS);
}

async function processJob(job) {
  const details = { template: job.template, account: job.account_id, job: job.id };
  const attempt = job.attempts + 1;
  try {
    const message = buildMessage(job);
    if (!message) {
      store.markEmailSkipped(job.id);
      return log(null, "email.skipped", { ...details, reason: "account_not_pending" });
    }
    await mailer.deliver(message);
    store.markEmailSent(job.id);
    log(null, "email.sent", { ...details, attempt });
  } catch (err) {
    const error = String(err.message || err).slice(0, 500);
    if (attempt >= MAX_ATTEMPTS) {
      store.markEmailFailed(job.id, error);
      return log(null, "email.failed", { ...details, attempt, error: JSON.stringify(error) });
    }
    const delay = backoffMs(attempt);
    store.markEmailRetry(job.id, new Date(Date.now() + delay).toISOString(), error);
    log(null, "email.retry", { ...details, attempt, retry_in_s: delay / 1000, error: JSON.stringify(error) });
  }
}

// sends everything that is due, one batch at a time, until the queue is empty

async function processQueue() {
  if (running) return;
  running = true;
  try {
    let jobs;
    while ((jobs = store.claimDueEmails(BATCH_SIZE)).length) {
      for (const job of jobs) await processJob(job);
    }
  } catch (err) {
    console.error(err.stack || err.message);
  } finally {
    running = false;
  }
}

// call after queueing an email so it goes out now instead of on the next poll

function kick() {
  setImmediate(processQueue);
}

function start() {
  const requeued = store.requeueStuckEmails();
  if (requeued) log(null, "email.requeued", { count: requeued });
  console.log(`Email worker sending via ${mailer.describe()}`);
  setInterval(processQueue, POLL_MS);
  kick();
}

module.exports = { start, kick };
