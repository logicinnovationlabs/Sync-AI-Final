"""
OAuth 2.1 routes: token issuance and revocation.

Provides:
- POST /oauth/token: token endpoint (authorization_code, refresh_token, client_credentials)
- POST /oauth/revoke: revocation endpoint
"""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Depends, Form

from app.api.deps import get_current_user, get_tenant
from app.core.exceptions import UnauthorizedError, ForbiddenError, TenantNotFoundError
from app.services.oauth_service import oauth_service
from app.services.revocation import revocation_service
from app.services.tenant_resolver import tenant_resolver
from app.storage.tenant_db import tenant_db_manager


router = APIRouter(prefix="/oauth", tags=["oauth"])


async def _tenant_session(tenant_id: str):
    try:
        routing = await tenant_resolver.resolve(str(tenant_id))
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=401, detail="Unknown tenant") from exc
    async for db_session in tenant_db_manager.get_session(
        routing.db_host,
        routing.db_name,
        routing.db_user,
        routing.db_password,
        str(tenant_id),
    ):
        yield db_session


@router.post("/token")
async def token_endpoint(
    grant_type: Literal["authorization_code", "refresh_token", "client_credentials"] = Form(...),
    code: Optional[str] = Form(None),
    redirect_uri: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    client_secret: Optional[str] = Form(None),
    refresh_token: Optional[str] = Form(None),
    code_verifier: Optional[str] = Form(None),
    scope: Optional[str] = Form(None),
    tenant_id: Optional[str] = Form(None),
):
    """
    OAuth 2.1 token endpoint.

    Supports authorization_code (PKCE), refresh_token, and client_credentials.
    """
    scopes = [s for s in (scope or "").split() if s]
    try:
        if grant_type == "client_credentials":
            if not client_id or not client_secret or not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail="client_id, client_secret, and tenant_id required",
                )
            async for db_session in _tenant_session(tenant_id):
                return await oauth_service.issue_tokens_for_client_credentials(
                    client_id=client_id,
                    client_secret=client_secret,
                    scopes=scopes,
                    db_session=db_session,
                )

        if grant_type == "refresh_token":
            if not refresh_token:
                raise HTTPException(status_code=400, detail="refresh_token required")
            from app.services.token_service import token_service

            payload = await token_service.validate_token(refresh_token)
            if payload.get("token_type") != "refresh":
                raise HTTPException(status_code=401, detail="Invalid token type")
            refresh_tenant = str(payload.get("tenant_id") or "")
            if not refresh_tenant:
                raise HTTPException(status_code=401, detail="Refresh token missing tenant_id")
            async for db_session in _tenant_session(refresh_tenant):
                return await oauth_service.refresh_access_token(refresh_token, db_session)

        if grant_type == "authorization_code":
            if not code or not redirect_uri or not code_verifier or not client_id:
                raise HTTPException(
                    status_code=400,
                    detail="code, redirect_uri, code_verifier, and client_id required",
                )
            code_data = await oauth_service.peek_authorization_code(code)
            if not code_data:
                raise HTTPException(status_code=401, detail="Invalid or expired authorization code")
            authz_tenant = str(code_data.get("tenant_id") or "")
            if not authz_tenant:
                raise HTTPException(status_code=401, detail="Authorization code missing tenant")
            async for db_session in _tenant_session(authz_tenant):
                return await oauth_service.exchange_authorization_code(
                    code=code,
                    code_verifier=code_verifier,
                    client_id=client_id,
                    redirect_uri=redirect_uri,
                    db_session=db_session,
                )

        raise HTTPException(status_code=400, detail=f"Unsupported grant_type: {grant_type}")
    except HTTPException:
        raise
    except UnauthorizedError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/revoke")
async def revoke_endpoint(
    token: str = Form(...),
    token_type_hint: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    tenant_routing: dict = Depends(get_tenant),
):
    """Revoke a token (access or refresh)."""
    tenant_id = str(tenant_routing.tenant_id)

    async for db_session in tenant_db_manager.get_session(
        tenant_routing.db_host,
        tenant_routing.db_name,
        tenant_routing.db_user,
        tenant_routing.db_password,
        tenant_id,
    ):
        await revocation_service.revoke_token(token, tenant_id, db_session)

    return {"message": "Token revoked successfully"}
