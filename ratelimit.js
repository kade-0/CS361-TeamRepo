// simple in-memory fixed window rate limiter, keyed by client IP unless a key function is given

function rateLimit({ windowMs, max, key = req => req.ip }) {
  const hits = new Map();
  setInterval(() => {
    const now = Date.now();
    hits.forEach((entry, k) => { if (entry.resetAt <= now) hits.delete(k); });
  }, windowMs).unref();

  return (req, res, next) => {
    const now = Date.now();
    const k = key(req);
    let entry = hits.get(k);
    if (!entry || entry.resetAt <= now) {
      entry = { count: 0, resetAt: now + windowMs };
      hits.set(k, entry);
    }
    entry.count++;
    if (entry.count <= max) return next();
    res.set("Retry-After", Math.ceil((entry.resetAt - now) / 1000));
    res.status(429).json({ error: "Too many requests. Wait a minute and try again." });
  };
}

module.exports = { rateLimit };
