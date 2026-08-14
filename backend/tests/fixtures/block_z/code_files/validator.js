/**
 * Input validation functions
 */

/**
 * Validate user registration data
 */
function validateUser(user) {
  const errors = [];
  
  if (!user.email || !isValidEmail(user.email)) {
    errors.push('Invalid email address');
  }
  
  if (!user.password || user.password.length < 8) {
    errors.push('Password must be at least 8 characters');
  }
  
  if (!user.firstName || user.firstName.trim().length === 0) {
    errors.push('First name is required');
  }
  
  if (!user.lastName || user.lastName.trim().length === 0) {
    errors.push('Last name is required');
  }
  
  if (errors.length > 0) {
    throw new ValidationError(errors.join(', '));
  }
  
  return true;
}

/**
 * Validate email format
 */
function isValidEmail(email) {
  const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return regex.test(email);
}

/**
 * Validate search query
 */
function validateSearchQuery(query) {
  if (!query.q || query.q.trim().length === 0) {
    throw new ValidationError('Search query is required');
  }
  
  if (query.q.length > 200) {
    throw new ValidationError('Search query too long');
  }
  
  return true;
}

class ValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = 'ValidationError';
    this.isOperational = true;
    this.statusCode = 400;
  }
}

module.exports = {
  validateUser,
  validateSearchQuery,
  isValidEmail,
  ValidationError
};
