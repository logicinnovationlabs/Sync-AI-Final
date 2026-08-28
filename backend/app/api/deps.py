"""
FastAPI dependencies for authentication and authorization.

Provides:
- get_current_user: decode JWT and return current user info
- get_tenant: resolve tenant routing from JWT
- require_scope: factory for scope-based authorization (A5 — contracts error envelope)
- require_matching_tenant: reject cross-tenant replay via X-Tenant-ID (A4)
- require_admin: Block N org-admin guard (DB-backed role + is_active)
"""

from typing import Any, AsyncGenerator, Callable, Dict, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InvalidTokenError,
    RevokedTokenError,
    ForbiddenError,
    CrossTenantAccessError,
    TenantNotFoundError,
    UnauthorizedError,
)
from app.models.user import User
from app.services.token_service import token_service
from app.services.tenant_resolver import tenant_resolver, TenantRouting
from app.storage.tenant_db import tenant_db_manager


security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    """
    Dependency to get the current authenticated user from JWT.
    
    Returns:
        Dict with token payload (contains tenant_id, principal_id, scopes, etc.).
        
    Raises:
        UnauthorizedError 401 if token is missing, invalid or revoked (error envelope via handler).
    """
    if not credentials or not credentials.credentials:
        raise UnauthorizedError("Not authenticated")
    try:
        token = credentials.credentials
        payload = await token_service.validate_token(token)
        return payload
    except (InvalidTokenError, RevokedTokenError) as e:
        raise UnauthorizedError(str(e))



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
        raise UnauthorizedError("Token missing tenant_id claim")
    
    try:
        routing = await tenant_resolver.resolve(tenant_id)
        return routing
    except TenantNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tenant resolution failed: {e}")


async def get_tenant_session(
    tenant: TenantRouting = Depends(get_tenant),
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a tenant-DB session bound to the JWT tenant_id."""
    factory = tenant_db_manager.get_session_factory(
        tenant.db_host,
        tenant.db_name,
        tenant.db_user,
        tenant.db_password,
        str(tenant.tenant_id),
    )
    session = factory()
    try:
        yield session
    finally:
        await session.close()


async def require_admin(
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
) -> Dict[str, Any]:
    """
    Block N admin guard: JWT must belong to an active user with role == 'admin'
    in the tenant DB. Role is never taken from the request body; tenant_id
    always comes from the JWT.
    """
    principal_raw = current_user.get("sub")
    if not principal_raw:
        raise UnauthorizedError("Token missing sub claim")
    try:
        principal_id = UUID(str(principal_raw))
        tenant_uuid = UUID(str(tenant.tenant_id))
    except (TypeError, ValueError):
        raise UnauthorizedError("Token identity is malformed")

    result = await db_session.execute(
        select(User).where(
            User.principal_id == principal_id,
            User.tenant_id == tenant_uuid,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise ForbiddenError("Admin role required")
    if not user.is_active or user.status != "active":
        raise ForbiddenError("Admin account is inactive")
    if user.role != "admin":
        raise ForbiddenError("Admin role required")

    current_user["role"] = user.role
    current_user["is_active"] = user.is_active
    current_user["principal_id"] = str(user.principal_id)
    return current_user


def require_scope(required_scope: str) -> Callable:
    """
    Factory function to create a scope-checking dependency.
    
    Missing scope raises ForbiddenError so the shared ErrorResponse envelope is used (A5).
    """

    async def scope_checker(current_user: Dict[str, Any] = Depends(get_current_user)):
        scopes = current_user.get("scopes", [])
        if required_scope not in scopes:
            raise ForbiddenError(f"Missing required scope: {required_scope}")
        return current_user

    return scope_checker


async def require_matching_tenant(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Enforce that the request's intended tenant (X-Tenant-ID) matches the JWT tenant_id.
    
    This is the storage of the A4 security boundary for tenant-scoped endpoints:
    presenting a tenant-A token to a tenant-B-scoped request is rejected with 403.
    """
    token_tenant = current_user.get("tenant_id")
    if not token_tenant:
        raise UnauthorizedError("Token missing tenant_id claim")
    if str(token_tenant) != str(x_tenant_id):
        raise CrossTenantAccessError(str(token_tenant), str(x_tenant_id))
    return current_user
