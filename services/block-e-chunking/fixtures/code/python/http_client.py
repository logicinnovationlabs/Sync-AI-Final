import requests
from typing import Dict, Any, Optional

class HTTPClient:
    """Synchronous HTTP client."""
    
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
    
    def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make GET request."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def post(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make POST request."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.post(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def put(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make PUT request."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.put(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def delete(self, endpoint: str) -> Dict[str, Any]:
        """Make DELETE request."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.delete(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def close(self):
        """Close session."""
        self.session.close()
