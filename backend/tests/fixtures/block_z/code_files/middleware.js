/**
 * Error handling middleware
 */

function errorHandler(err, req, res, next) {
  console.error(err.stack);
  
  // Operational errors
  if (err.isOperational) {
    return res.status(err.statusCode || 500).json({
      error: {
        message: err.message,
        code: err.code
      }
    });
  }
  
  // Programming or unknown errors
  res.status(500).json({
    error: {
      message: 'Internal server error',
      code: 'INTERNAL_ERROR'
    }
  });
}

function notFoundHandler(req, res, next) {
  res.status(404).json({
    error: {
      message: 'Resource not found',
      code: 'NOT_FOUND'
    }
  });
}

function asyncHandler(fn) {
  return (req, res, next) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

module.exports = {
  errorHandler,
  notFoundHandler,
  asyncHandler
};
