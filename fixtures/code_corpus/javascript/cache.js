/**
 * In-memory cache with TTL support
 */

class Cache {
  constructor(defaultTTL = 3600000) {
    this.cache = new Map();
    this.defaultTTL = defaultTTL;
    this.timers = new Map();
  }

  set(key, value, ttl = this.defaultTTL) {
    // Clear existing timer if key exists
    if (this.timers.has(key)) {
      clearTimeout(this.timers.get(key));
    }

    // Store value
    this.cache.set(key, value);

    // Set expiration timer
    const timer = setTimeout(() => {
      this.delete(key);
    }, ttl);

    this.timers.set(key, timer);
  }

  get(key) {
    return this.cache.get(key);
  }

  has(key) {
    return this.cache.has(key);
  }

  delete(key) {
    this.cache.delete(key);
    if (this.timers.has(key)) {
      clearTimeout(this.timers.get(key));
      this.timers.delete(key);
    }
  }

  clear() {
    this.cache.clear();
    this.timers.forEach(timer => clearTimeout(timer));
    this.timers.clear();
  }

  size() {
    return this.cache.size;
  }

  keys() {
    return Array.from(this.cache.keys());
  }

  values() {
    return Array.from(this.cache.values());
  }

  getOrSet(key, factory, ttl = this.defaultTTL) {
    if (this.has(key)) {
      return this.get(key);
    }
    const value = factory();
    this.set(key, value, ttl);
    return value;
  }
}

module.exports = Cache;
