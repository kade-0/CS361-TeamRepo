function log(req, event, details = {}) {
  const parts = Object.entries(details).map(([key, value]) => `${key}=${value}`);
  console.log([new Date().toISOString(), req ? req.ip : "-", event, ...parts].join(" "));
}

// masks an email address for logging purposes

function maskEmail(email) {
  if (typeof email !== "string" || !email.includes("@")) return "-";
  const [name, domain] = email.trim().split("@");
  return `${name[0] || ""}***@${domain}`;
}

function requestLogger(req, res, next) {
  const start = process.hrtime.bigint();
  res.on("finish", () => {
    const ms = Number(process.hrtime.bigint() - start) / 1e6;
    log(req, "request", { method: req.method, path: req.path, status: res.statusCode, ms: ms.toFixed(1) });
  });
  next();
}

module.exports = { log, maskEmail, requestLogger };
