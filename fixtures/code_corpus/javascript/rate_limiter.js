/**
 * Rate limiter using sliding window algorithm
 */

class RateLimiter {
  constructor(maxRequests, windowMs) {
    this.maxRequests = maxRequests;
    this.windowMs = windowMs;
    this.requests = new Map();
  }

  _cleanup(key) {
    const now = Date.now();
    const timestamps = this.requests.get(key) || [];
    const validTimestamps = timestamps.filter(ts => ts > now - this.windowMs);
    
    if (validTimestamps.length === 0) {
      this.requests.delete(key);
    } else {
      this.requests.set(key, validTimestamps);
    }
  }

  check(key) {
    this._cleanup(key);
    const timestamps = this.requests.get(key) || [];
    return timestamps.length < this.maxRequests;
  }

  hit(key) {
    const now = Date.now();
    if (!this.requests.has(key)) {
      this.requests.set(key, []);
    }
    this.requests.get(key).push(now);
    this._cleanup(key);
  }

  getRemaining(key) {
    this._cleanup(key);
    const timestamps = this.requests.get(key) || [];
    return Math.max(0, this.maxRequests - timestamps.length);
  }

  getResetTime(key) {
    const timestamps = this.requests.get(key);
    if (!timestamps || timestamps.length === 0) {
      return 0;
    }
    return timestamps[0] + this.windowMs;
  }

  reset(key) {
    this.requests.delete(key);
  }

  resetAll() {
    this.requests.clear();
  }
}

module.exports = RateLimiter;
