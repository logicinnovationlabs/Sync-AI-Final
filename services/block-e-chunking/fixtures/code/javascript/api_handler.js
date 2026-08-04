/**
 * API Handler for HTTP requests
 */

class APIHandler {
  constructor(baseURL, timeout = 30000) {
    this.baseURL = baseURL.replace(/\/$/, '');
    this.timeout = timeout;
  }

  async get(endpoint, params = {}) {
    const url = new URL(`${this.baseURL}/${endpoint.replace(/^\//, '')}`);
    Object.keys(params).forEach(key => 
      url.searchParams.append(key, params[key])
    );

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(this.timeout)
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  }

  async post(endpoint, data = {}) {
    const url = `${this.baseURL}/${endpoint.replace(/^\//, '')}`;
    
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(this.timeout)
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  }

  async put(endpoint, data = {}) {
    const url = `${this.baseURL}/${endpoint.replace(/^\//, '')}`;
    
    const response = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(this.timeout)
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  }

  async delete(endpoint) {
    const url = `${this.baseURL}/${endpoint.replace(/^\//, '')}`;
    
    const response = await fetch(url, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(this.timeout)
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  }
}

module.exports = APIHandler;
