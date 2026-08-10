/**
 * Data transformation utilities
 */

class DataTransformer {
  constructor(config = {}) {
    this.config = {
      normalize: config.normalize || false,
      filterNulls: config.filterNulls || true,
      ...config
    };
  }

  transform(data) {
    let result = data;

    if (this.config.filterNulls) {
      result = this._filterNulls(result);
    }

    if (this.config.normalize) {
      result = this._normalize(result);
    }

    return result;
  }

  _filterNulls(data) {
    if (Array.isArray(data)) {
      return data.filter(item => item !== null && item !== undefined);
    }

    if (typeof data === 'object' && data !== null) {
      const filtered = {};
      for (const [key, value] of Object.entries(data)) {
        if (value !== null && value !== undefined) {
          filtered[key] = value;
        }
      }
      return filtered;
    }

    return data;
  }

  _normalize(data) {
    if (Array.isArray(data)) {
      return data.map(item => this._normalize(item));
    }

    if (typeof data === 'object' && data !== null) {
      const normalized = {};
      for (const [key, value] of Object.entries(data)) {
        const normalizedKey = key.toLowerCase().replace(/[^a-z0-9]/g, '_');
        normalized[normalizedKey] = this._normalize(value);
      }
      return normalized;
    }

    if (typeof data === 'string') {
      return data.toLowerCase().trim();
    }

    return data;
  }

  batchTransform(items) {
    return items.map(item => this.transform(item));
  }

  aggregate(items, key, aggregator = 'sum') {
    const values = items.map(item => item[key]).filter(v => v !== null && v !== undefined);

    switch (aggregator) {
      case 'sum':
        return values.reduce((a, b) => a + b, 0);
      case 'avg':
        return values.reduce((a, b) => a + b, 0) / values.length;
      case 'min':
        return Math.min(...values);
      case 'max':
        return Math.max(...values);
      case 'count':
        return values.length;
      default:
        throw new Error(`Unknown aggregator: ${aggregator}`);
    }
  }
}

module.exports = DataTransformer;
