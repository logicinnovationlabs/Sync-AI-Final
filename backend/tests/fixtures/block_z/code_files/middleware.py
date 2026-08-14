"""Middleware for request/response handling."""
from typing import Callable
import time

def auth_middleware(get_response: Callable):
    """Authentication middleware."""
    def middleware(request):
        token = request.headers.get("Authorization")
        if not token or not token.startswith("Bearer "):
            raise Exception("Unauthorized: Missing or invalid token")
        
        # Verify token (simplified)
        request.user = {"id": "user123", "email": "user@example.com"}
        response = get_response(request)
        return response
    
    return middleware

def logging_middleware(get_response: Callable):
    """Logging middleware."""
    def middleware(request):
        start_time = time.time()
        print(f"Request: {request.method} {request.path}")
        
        response = get_response(request)
        
        elapsed = time.time() - start_time
        print(f"Response: {response.status_code} ({elapsed:.3f}s)")
        return response
    
    return middleware

def cors_middleware(get_response: Callable):
    """CORS middleware."""
    def middleware(request):
        response = get_response(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
    
    return middleware

def rate_limit_middleware(get_response: Callable, max_requests: int = 100):
    """Rate limiting middleware."""
    request_counts = {}
    
    def middleware(request):
        client_ip = request.META.get("REMOTE_ADDR")
        current_time = int(time.time() / 60)  # Per minute
        key = f"{client_ip}:{current_time}"
        
        count = request_counts.get(key, 0)
        if count >= max_requests:
            raise Exception("Rate limit exceeded")
        
        request_counts[key] = count + 1
        return get_response(request)
    
    return middleware
