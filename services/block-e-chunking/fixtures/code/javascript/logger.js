/**
 * Structured logging utility
 */

class Logger {
  constructor(name, level = 'info') {
    this.name = name;
    this.level = this._parseLevel(level);
    this.levels = {
      debug: 0,
      info: 1,
      warn: 2,
      error: 3
    };
  }

  _parseLevel(level) {
    return this.levels[level.toLowerCase()] || 1;
  }

  _shouldLog(level) {
    return this.levels[level] >= this.level;
  }

  _format(level, message, context = {}) {
    const timestamp = new Date().toISOString();
    return JSON.stringify({
      timestamp,
      level: level.toUpperCase(),
      logger: this.name,
      message,
      ...context
    });
  }

  debug(message, context = {}) {
    if (this._shouldLog('debug')) {
      console.log(this._format('debug', message, context));
    }
  }

  info(message, context = {}) {
    if (this._shouldLog('info')) {
      console.log(this._format('info', message, context));
    }
  }

  warn(message, context = {}) {
    if (this._shouldLog('warn')) {
      console.warn(this._format('warn', message, context));
    }
  }

  error(message, context = {}) {
    if (this._shouldLog('error')) {
      console.error(this._format('error', message, context));
    }
  }

  static create(name, level = 'info') {
    return new Logger(name, level);
  }
}

module.exports = Logger;
