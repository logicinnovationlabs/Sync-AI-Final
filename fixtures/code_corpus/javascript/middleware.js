/**
 * Express middleware utilities
 */

class Middleware {
  static errorHandler(err, req, res, next) {
    console.error('Error:', err);

    if (err.type === 'entity.parse.failed') {
      return res.status(400).json({
        error: 'Invalid JSON',
        message: err.message
      });
    }

    if (err.name === 'ValidationError') {
      return res.status(400).json({
        error: 'Validation Error',
        message: err.message
      });
    }

    res.status(500).json({
      error: 'Internal Server Error',
      message: process.env.NODE_ENV === 'development' ? err.message : undefined
    });
  }

  static requestLogger(req, res, next) {
    const start = Date.now();

    res.on('finish', () => {
      const duration = Date.now() - start;
      console.log(`${req.method} ${req.path} ${res.statusCode} ${duration}ms`);
    });

    next();
  }

  static tenantId(req, res, next) {
    const tenantId = req.headers['x-tenant-id'] || req.headers['X-Tenant-ID'];

    if (!tenantId) {
      return res.status(400).json({
        error: 'Missing Tenant ID',
        message: 'X-Tenant-ID header is required'
      });
    }

    req.tenantId = tenantId;
    next();
  }

  static async auth(req, res, next) {
    const token = req.headers.authorization?.replace('Bearer ', '');

    if (!token) {
      return res.status(401).json({
        error: 'Unauthorized',
        message: 'Missing authentication token'
      });
    }

    try {
      // Verify token (implementation depends on auth system)
      req.user = { id: 'user_123' }; // Placeholder
      next();
    } catch (error) {
      res.status(401).json({
        error: 'Unauthorized',
        message: 'Invalid token'
      });
    }
  }

  static cors(req, res, next) {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Tenant-ID');

    if (req.method === 'OPTIONS') {
      return res.sendStatus(204);
    }

    next();
  }
}

module.exports = Middleware;
