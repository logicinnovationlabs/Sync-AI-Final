"""
Auth routes: Native email/password and OIDC login.

Provides:
- POST /auth/login: native email/password login
- GET /auth/sso/login: redirect to OIDC provider
- GET /auth/sso/callback: handle OIDC callback, issue JWT
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
import httpx

from app.core.config import settings
from app.services.token_service import token_service
from app.services.native_auth import native_auth_service
from app.services.tenant_resolver import tenant_resolver
from app.storage.tenant_db import tenant_db_manager


router = APIRouter(prefix="/auth", tags=["auth"])


class NativeLoginRequest(BaseModel):
    """Native login request with email and password."""
    
    email: EmailStr
    password: str
    tenant_subdomain: str  # To resolve which tenant the user belongs to


class NativeLoginResponse(BaseModel):
    """Native login response with JWT tokens."""
    
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


@router.post("/login", response_model=NativeLoginResponse)
async def native_login(request: NativeLoginRequest):
    """
    Native email/password login.
    
    Flow:
    1. Resolve tenant by subdomain
    2. Authenticate user with email/password
    3. Issue JWT tokens
    
    Args:
        request: Login credentials (email, password, tenant_subdomain)
        
    Returns:
        Access token, refresh token, and expiry.
        
    Raises:
        HTTPException 401 if credentials are invalid.
        HTTPException 404 if tenant not found.
    """
    # Resolve tenant by subdomain
    # In production, query the tenants table by subdomain
    from sqlalchemy import select
    from app.models.tenant import Tenant
    from app.storage.control_plane_db import ControlPlaneSessionLocal
    
    async with ControlPlaneSessionLocal() as control_session:
        stmt = select(Tenant).where(Tenant.subdomain == request.tenant_subdomain)
        result = await control_session.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            raise HTTPException(
                status_code=404,
                detail=f"Tenant not found: {request.tenant_subdomain}",
            )
        
        tenant_id = tenant.tenant_id
    
    # Resolve tenant routing
    try:
        routing = await tenant_resolver.resolve(str(tenant_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tenant resolution failed: {e}")
    
    # Get tenant database session
    async for db_session in tenant_db_manager.get_session(
        routing.db_host,
        routing.db_name,
        routing.db_user,
        routing.db_password,
        str(tenant_id),
    ):
        # Authenticate user
        try:
            user = await native_auth_service.authenticate_user(
                email=request.email,
                password=request.password,
                tenant_id=tenant_id,
                db_session=db_session,
            )
        except Exception as e:
            raise HTTPException(status_code=401, detail=str(e))
        
        # Issue JWT tokens
        access_token = await token_service.issue_access_token(
            tenant_id=str(tenant_id),
            principal_id=str(user.principal_id),
            scopes=["search.read", "document.read"],  # Default scopes for native users
        )
        
        refresh_token = await token_service.issue_refresh_token(
            tenant_id=str(tenant_id),
            principal_id=str(user.principal_id),
        )
        
        return NativeLoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.token_ttl_access,
        )


@router.get("/sso/login")
async def sso_login(redirect_uri: Optional[str] = None):
    """
    Initiate OIDC/SSO login flow.
    
    Redirects to the OIDC provider's authorization endpoint.
    
    Args:
        redirect_uri: Optional override for redirect_uri
        
    Returns:
        Redirect to OIDC provider.
    """
    if not settings.oidc_issuer or not settings.oidc_client_id:
        raise HTTPException(
            status_code=500,
            detail="OIDC not configured (OIDC_ISSUER and OIDC_CLIENT_ID required)",
        )
    
    # Build authorization URL
    redirect = redirect_uri or settings.oidc_redirect_uri
    auth_url = (
        f"{settings.oidc_issuer}/authorize"
        f"?client_id={settings.oidc_client_id}"
        f"&redirect_uri={redirect}"
        f"&response_type=code"
        f"&scope=openid profile email"
    )
    
    return RedirectResponse(url=auth_url)


@router.get("/sso/callback")
async def sso_callback(
    code: str = Query(..., description="Authorization code from OIDC provider"),
    state: Optional[str] = Query(None),
):
    """
    Handle OIDC/SSO callback and issue JWT.
    
    Args:
        code: Authorization code from OIDC provider
        state: Optional state parameter
        
    Returns:
        JWT access and refresh tokens.
    """
    if not settings.oidc_issuer or not settings.oidc_client_id or not settings.oidc_client_secret:
        raise HTTPException(
            status_code=500,
            detail="OIDC not configured",
        )
    
    # Exchange code for tokens
    token_url = f"{settings.oidc_issuer}/token"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.oidc_redirect_uri,
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
            },
        )
    
    if response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to exchange authorization code: {response.text}",
        )
    
    oidc_tokens = response.json()
    
    # For now, return a stub response (full implementation requires user lookup)
    # In production, decode id_token, look up user by email, issue our own JWT
    return {
        "message": "OIDC callback received (full implementation pending)",
        "oidc_tokens": oidc_tokens,
    }
