"""
OAuth 2.1 routes: token issuance and revocation.

Provides:
- POST /oauth/token: token endpoint (authorization_code, refresh_token, client_credentials)
- POST /oauth/revoke: revocation endpoint
"""

from typing import Literal, Optional
from fastapi import APIRouter, HTTPException, Depends, Form
from pydantic import BaseModel

from app.api.deps import get_current_user, get_tenant
from app.services.oauth_service import oauth_service
from app.services.revocation import revocation_service
from app.storage.tenant_db import tenant_db_manager


router = APIRouter(prefix="/oauth", tags=["oauth"])


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
):
    """
    OAuth 2.1 token endpoint.
    
    Supports:
    - authorization_code (with PKCE)
    - refresh_token
    - client_credentials
    
    Returns:
        Access token (and refresh token for authorization_code/refresh_token flows).
    """
    if grant_type == "client_credentials":
        if not client_id or not client_secret:
            raise HTTPException(status_code=400, detail="client_id and client_secret required")
        
        # For client_credentials, we need a way to resolve tenant_id
        # This is a stub; in prod, look up client by client_id to get tenant_id
        raise HTTPException(status_code=501, detail="client_credentials flow not yet implemented")
    
    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(status_code=400, detail="refresh_token required")
        
        # This is a stub; full implementation requires tenant DB session
        raise HTTPException(status_code=501, detail="refresh_token flow not yet implemented")
    
    elif grant_type == "authorization_code":
        if not code or not redirect_uri or not code_verifier:
            raise HTTPException(
                status_code=400,
                detail="code, redirect_uri, and code_verifier required",
            )
        
        # This is a stub; full implementation in production
        raise HTTPException(status_code=501, detail="authorization_code flow not yet implemented")
    
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported grant_type: {grant_type}")


@router.post("/revoke")
async def revoke_endpoint(
    token: str = Form(...),
    token_type_hint: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    tenant_routing: dict = Depends(get_tenant),
):
    """
    Revoke a token.
    
    Args:
        token: Token to revoke
        token_type_hint: Optional hint ('access_token' or 'refresh_token')
        
    Returns:
        Success message.
    """
    tenant_id = str(tenant_routing.tenant_id)
    
    # Get tenant DB session
    async for db_session in tenant_db_manager.get_session(
        tenant_routing.db_host,
        tenant_routing.db_name,
        tenant_routing.db_user,
        tenant_routing.db_password,
        tenant_id,
    ):
        await revocation_service.revoke_token(token, tenant_id, db_session)
    
    return {"message": "Token revoked successfully"}
