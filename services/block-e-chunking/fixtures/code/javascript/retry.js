/**
 * Retry utility with exponential backoff
 */

class Retry {
  constructor(options = {}) {
    this.maxAttempts = options.maxAttempts || 3;
    this.initialDelay = options.initialDelay || 1000;
    this.maxDelay = options.maxDelay || 30000;
    this.backoffMultiplier = options.backoffMultiplier || 2;
    this.retryableErrors = options.retryableErrors || [
      'ECONNRESET',
      'ETIMEDOUT',
      'ECONNREFUSED'
    ];
  }

  async execute(fn, context = null) {
    let lastError;
    let delay = this.initialDelay;

    for (let attempt = 1; attempt <= this.maxAttempts; attempt++) {
      try {
        return await fn.call(context, attempt);
      } catch (error) {
        lastError = error;

        if (!this._isRetryable(error)) {
          throw error;
        }

        if (attempt === this.maxAttempts) {
          throw error;
        }

        await this._sleep(delay);
        delay = Math.min(delay * this.backoffMultiplier, this.maxDelay);
      }
    }

    throw lastError;
  }

  _isRetryable(error) {
    if (this.retryableErrors.includes(error.code)) {
      return true;
    }
    if (error.statusCode >= 500) {
      return true;
    }
    if (error.statusCode === 429) {
      return true;
    }
    return false;
  }

  _sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  static create(options) {
    return new Retry(options);
  }
}

module.exports = Retry;
