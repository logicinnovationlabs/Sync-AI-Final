/**
 * Input validation utilities
 */

class Validator {
  static email(email) {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(email);
  }

  static username(username) {
    return /^[a-zA-Z0-9_]{3,30}$/.test(username);
  }

  static password(password) {
    if (password.length < 8) {
      return { valid: false, error: 'Password must be at least 8 characters' };
    }
    if (!/[A-Z]/.test(password)) {
      return { valid: false, error: 'Password must contain at least one uppercase letter' };
    }
    if (!/[a-z]/.test(password)) {
      return { valid: false, error: 'Password must contain at least one lowercase letter' };
    }
    if (!/[0-9]/.test(password)) {
      return { valid: false, error: 'Password must contain at least one digit' };
    }
    return { valid: true };
  }

  static url(url) {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  }

  static uuid(uuid) {
    const regex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    return regex.test(uuid);
  }

  static object(obj, schema) {
    const errors = [];

    for (const [field, rules] of Object.entries(schema)) {
      const value = obj[field];

      if (rules.required && (value === undefined || value === null)) {
        errors.push(`${field} is required`);
        continue;
      }

      if (value !== undefined && value !== null) {
        if (rules.type && typeof value !== rules.type) {
          errors.push(`${field} must be of type ${rules.type}`);
        }
        if (rules.min && value.length < rules.min) {
          errors.push(`${field} must be at least ${rules.min} characters`);
        }
        if (rules.max && value.length > rules.max) {
          errors.push(`${field} must be at most ${rules.max} characters`);
        }
        if (rules.pattern && !rules.pattern.test(value)) {
          errors.push(`${field} does not match required pattern`);
        }
      }
    }

    return errors.length === 0 ? { valid: true } : { valid: false, errors };
  }
}

module.exports = Validator;
