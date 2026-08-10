/**
 * Authentication utilities
 */

class Auth {
  constructor(secretKey) {
    this.secretKey = secretKey;
  }

  hashPassword(password) {
    // Simple hash - in production use bcrypt
    let hash = 0;
    for (let i = 0; i < password.length; i++) {
      const char = password.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return hash.toString(16);
  }

  verifyPassword(password, hash) {
    return this.hashPassword(password) === hash;
  }

  generateToken(user) {
    const payload = {
      userId: user.id,
      email: user.email,
      timestamp: Date.now()
    };
    return Buffer.from(JSON.stringify(payload)).toString('base64');
  }

  decodeToken(token) {
    try {
      const payload = Buffer.from(token, 'base64').toString('utf-8');
      return JSON.parse(payload);
    } catch {
      return null;
    }
  }
}

module.exports = Auth;
