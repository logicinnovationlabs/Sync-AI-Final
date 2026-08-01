"""
FastAPI dependencies for authentication and authorization.

Provides:
- get_current_user: decode JWT and return current user info
- get_tenant: resolve tenant routing from JWT
- require_scope: factory for scope-based authorization
"""

from typing import Dict, Any, Callable
from fastapi import Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.exceptions import (
    InvalidTokenError,
    RevokedTokenError,
    ForbiddenError,
    TenantNotFoundError,
)
from app.services.token_service import token_service
from app.services.tenant_resolver import tenant_resolver, TenantRouting


security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """
    Dependency to get the current authenticated user from JWT.
    
    Returns:
        Dict with token payload (contains tenant_id, principal_id, scopes, etc.).
        
    Raises:
        HTTPException 401 if token is invalid or revoked.
    """
    try:
        token = credentials.credentials
        payload = await token_service.validate_token(token)
        return payload
    except (InvalidTokenError, RevokedTokenError) as e:
        raise HTTPException(status_code=401, detail=str(e))


async def get_tenant(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> TenantRouting:
    """
    Dependency to resolve tenant routing from the current user's JWT.
    
    Returns:
        TenantRouting with database connection details.
        
    Raises:
        HTTPException 404 if tenant not found.
        HTTPException 500 if tenant resolution fails.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")
    
    try:
        routing = await tenant_resolver.resolve(tenant_id)
        return routing
    except TenantNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tenant resolution failed: {e}")


def require_scope(required_scope: str) -> Callable:
    """
    Factory function to create a scope-checking dependency.
    
    Args:
        required_scope: Scope name (e.g., 'search.read')
        
    Returns:
        FastAPI dependency function.
        
    Example:
        @app.get("/search", dependencies=[Depends(require_scope("search.read"))])
    """

    async def scope_checker(current_user: Dict[str, Any] = Depends(get_current_user)):
        scopes = current_user.get("scopes", [])
        if required_scope not in scopes:
            raise HTTPException(
                status_code=403,
                detail=f"Missing required scope: {required_scope}",
            )
        return current_user

    return scope_checker
