"""
Tenant middleware: resolves tenant from JWT and attaches to request.state.

This middleware extracts tenant_id from the JWT and resolves the tenant routing
before the request reaches the route handler. Resolution failures are non-fatal:
route-level auth deps remain the source of truth for 401/403.

Expected soft-fails (missing tenant, bad JWT, not-yet-migrated schema) log at
DEBUG. Unexpected exceptions (e.g. pool/event-loop errors) still soft-fail so
this optional pre-resolve cannot take down the ASGI cycle, but log at WARNING
so infrastructure failures are not silent.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import logging

import jwt
from sqlalchemy.exc import SQLAlchemyError
from opentelemetry import trace

from app.core.exceptions import TenantNotFoundError, VaultError
from app.services.token_service import token_service
from app.services.tenant_resolver import tenant_resolver

logger = logging.getLogger(__name__)

# Expected soft-fail cases for optional tenant pre-resolve.
_EXPECTED_SOFT_FAIL = (
    TenantNotFoundError,
    VaultError,
    jwt.PyJWTError,
    SQLAlchemyError,  # includes ProgrammingError (missing table), OperationalError
    ValueError,
    KeyError,
    OSError,
)


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Tenant resolution middleware.
    
    Extracts tenant_id from JWT, resolves routing, and attaches to request.state.tenant.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip tenant resolution for public endpoints
        if request.url.path in ["/", "/docs", "/openapi.json", "/health", "/redoc"]:
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
                    # Set tenant.id on current span for trace correlation (§2.5)
                    span = trace.get_current_span()
                    if span and span.is_recording():
                        span.set_attribute("tenant.id", tenant_id)
            except _EXPECTED_SOFT_FAIL as e:
                # Expected: missing tenant, bad JWT shape, schema/DB soft errors.
                # Route-level auth deps remain the real 401/403 gate.
                logger.debug("Tenant middleware soft-fail: %s", e)
            except Exception as e:
                # Still soft-fail (middleware is optional pre-resolve) but never silent:
                # surface type+message at WARNING so pool exhaustion / loop bugs are visible.
                logger.warning(
                    "Tenant middleware unexpected soft-fail (%s): %s",
                    type(e).__name__,
                    e,
                )
        
        response = await call_next(request)
        return response
