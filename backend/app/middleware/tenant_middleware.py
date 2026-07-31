"""
Tenant middleware: resolves tenant from JWT and attaches to request.state.

This middleware extracts tenant_id from the JWT and resolves the tenant routing
before the request reaches the route handler.
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable

from app.services.token_service import token_service
from app.services.tenant_resolver import tenant_resolver
from app.core.exceptions import TenantNotFoundError, InvalidTokenError


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Tenant resolution middleware.
    
    Extracts tenant_id from JWT, resolves routing, and attaches to request.state.tenant.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip tenant resolution for public endpoints
        if request.url.path in ["/docs", "/openapi.json", "/health"]:
            return await call_next(request)
        
        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            
            try:
                # Decode token (without full validation for performance)
                payload = await token_service.decode_without_validation(token)
                tenant_id = payload.get("tenant_id")
                
                if tenant_id:
                    # Resolve tenant and attach to request state
                    routing = await tenant_resolver.resolve(tenant_id)
                    request.state.tenant = routing
            except (TenantNotFoundError, InvalidTokenError):
                # Let the route handler deal with auth failures
                pass
        
        response = await call_next(request)
        return response
