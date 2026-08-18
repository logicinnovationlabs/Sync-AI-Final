"""Tenant/user binding for MCP. JWT string claims only — no control-plane UUID resolver."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID, uuid5, NAMESPACE_URL

from fastapi import Depends, HTTPException, Request

from app.api.deps import get_current_user
from app.core.exceptions import UnauthorizedError
from app.services.mcp_gateway.revocation import mcp_session_cache


def mcp_principal_id(current_user: Dict[str, Any]) -> str:
    return str(
        current_user.get("sub")
        or current_user.get("principal_id")
        or current_user.get("user_id")
        or ""
    )


def mcp_tenant_id(current_user: Dict[str, Any]) -> str:
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise UnauthorizedError("Token missing tenant_id claim")
    return str(tenant_id)


def actor_id_for_audit(principal_id: str) -> UUID:
    """Map JWT principal to audit_logs.actor_id (UUID column, unchanged).

    UUID-shaped claims are stored as-is. Opaque principals (OAuth client_id,
    test slugs) are not UUID()-cast — that throws. They become a stable
    UUID5 and the raw principal is always written to target_json['user'].
    """
    try:
        return UUID(principal_id)
    except (ValueError, TypeError, AttributeError):
        return uuid5(NAMESPACE_URL, f"mcp.actor:{principal_id}")


async def get_mcp_identity(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Authenticated MCP identity. Tenant is the JWT string claim."""
    tenant_id = mcp_tenant_id(current_user)
    principal_id = mcp_principal_id(current_user)
    if not principal_id:
        raise UnauthorizedError("Token missing sub claim")
    jti = str(current_user.get("jti") or "")

    if mcp_session_cache.is_revoked(tenant_id, jti=jti, principal_id=principal_id):
        raise UnauthorizedError("Session has been revoked")

    mcp_session_cache.remember(tenant_id, jti=jti, principal_id=principal_id)
    request.state.mcp_tenant_id = tenant_id
    request.state.mcp_principal_id = principal_id
    request.state.mcp_jti = jti
    return current_user


def reject_impersonation(
    current_user: Dict[str, Any],
    *,
    body_tenant_id: Optional[str] = None,
    body_user_id: Optional[str] = None,
    arguments: Optional[Dict[str, Any]] = None,
) -> None:
    """Identity is JWT-only. Any attempt to bind a different tenant/user is 403."""
    token_tenant = mcp_tenant_id(current_user)
    token_principal = mcp_principal_id(current_user)
    args = arguments or {}
    candidates = [
        body_tenant_id,
        args.get("tenant_id"),
    ]
    for claimed in candidates:
        if claimed is not None and str(claimed) != token_tenant:
            raise HTTPException(status_code=403, detail="Tenant impersonation denied")
    user_candidates = [
        body_user_id,
        args.get("user_id"),
        args.get("principal_id"),
        args.get("actor_id"),
    ]
    for claimed in user_candidates:
        if claimed is not None and str(claimed) != token_principal:
            raise HTTPException(status_code=403, detail="User impersonation denied")
