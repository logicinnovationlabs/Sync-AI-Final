"""
Auth routes: Native email/password and OIDC login.

Provides:
- POST /auth/login: native email/password login
- GET /auth/sso/login: redirect to OIDC provider
- GET /auth/sso/callback: handle OIDC callback, issue JWT
"""

from typing import Annotated, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import AfterValidator, BaseModel
from email_validator import EmailNotValidError, validate_email
import httpx
import hashlib
import secrets
import base64
from datetime import datetime, timezone
from urllib.parse import urlencode
import jwt as pyjwt
import logging

from app.core.config import settings
from app.services.token_service import token_service
from app.services.native_auth import native_auth_service
from app.services.tenant_resolver import tenant_resolver
from app.services.admin.scopes import scopes_for_role
from app.services.oauth_service import oauth_service
from app.storage.tenant_db import tenant_db_manager
from app.storage.redis_client import redis_client

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/auth", tags=["auth"])

OIDC_STATE_PARTITION = "oidc"
ALLOWED_OIDC_REDIRECT_PREFIXES = (
    "http://localhost",
    "https://localhost",
)


router = APIRouter(prefix="/auth", tags=["auth"])


def _login_email(value: str) -> str:
    """Accept reserved TLDs such as .test so seeded member@alpha.test can sign in."""
    try:
        result = validate_email(
            value, check_deliverability=False, test_environment=True
        )
        return result.normalized
    except EmailNotValidError as exc:
        raise ValueError("Enter a valid email address.") from exc


LoginEmail = Annotated[str, AfterValidator(_login_email)]


class NativeLoginRequest(BaseModel):
    """Native login request with email and password."""

    email: LoginEmail
    password: str
    tenant_subdomain: str  # To resolve which tenant the user belongs to


class NativeLoginResponse(BaseModel):
    """Native login response with JWT tokens."""
    
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    role: str = "member"
    must_change_password: bool = False


class RefreshRequest(BaseModel):
    """SPA refresh body (frontend calls POST /auth/refresh)."""

    refresh_token: str


@router.post("/refresh", response_model=NativeLoginResponse)
async def refresh_session(request: RefreshRequest):
    """Mint a new access + refresh token pair from a valid refresh JWT.

    The UI uses JSON ``{ refresh_token }`` here. The OAuth form endpoint
    ``POST /oauth/token`` remains for protocol clients.
    """
    from app.core.exceptions import UnauthorizedError, TenantNotFoundError

    try:
        payload = await token_service.validate_token(request.refresh_token)
        if payload.get("token_type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        tenant_id = str(payload.get("tenant_id") or "")
        if not tenant_id:
            raise HTTPException(status_code=401, detail="Refresh token missing tenant_id")
        routing = await tenant_resolver.resolve(tenant_id)
        async for db_session in tenant_db_manager.get_session(
            routing.db_host,
            routing.db_name,
            routing.db_user,
            routing.db_password,
            tenant_id,
        ):
            tokens = await oauth_service.refresh_access_token(
                request.refresh_token, db_session
            )
            return NativeLoginResponse(
                access_token=tokens["access_token"],
                refresh_token=tokens["refresh_token"],
                token_type=tokens.get("token_type", "Bearer"),
                expires_in=int(tokens.get("expires_in") or settings.token_ttl_access),
            )
    except HTTPException:
        raise
    except UnauthorizedError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=401, detail="Unknown tenant") from exc


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
    factory = tenant_db_manager.get_session_factory(
        routing.db_host,
        routing.db_name,
        routing.db_user,
        routing.db_password,
        str(tenant_id),
    )
    db_session = factory()
    try:
        # Authenticate user
        user = await native_auth_service.authenticate_user(
            email=request.email,
            password=request.password,
            tenant_id=tenant_id,
            db_session=db_session,
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    # Issue JWT tokens — scopes follow persisted org role (Block N)
    role = getattr(user, "role", None) or "member"
    scopes = scopes_for_role(role)
    access_token = await token_service.issue_access_token(
        tenant_id=str(tenant_id),
        principal_id=str(user.principal_id),
        scopes=scopes,
        role=role,
        token_version=getattr(user, "token_version", 0) or 0,
        must_change_password=bool(getattr(user, "must_change_password", False)),
    )
    
    refresh_token = await token_service.issue_refresh_token(
        tenant_id=str(tenant_id),
        principal_id=str(user.principal_id),
    )
    await oauth_service.persist_refresh_token(
        refresh_token,
        str(tenant_id),
        str(user.principal_id),
        db_session,
    )

    try:
        from app.storage.canonical_repo import bind_pending_drive_shares

        await bind_pending_drive_shares(
            db_session, tenant_id, user.email, user.principal_id
        )
    except Exception:
        logger.exception(
            "pending identity drain failed at login email=%s tenant_id=%s",
            user.email,
            tenant_id,
        )

    result = NativeLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.token_ttl_access,
        role=role,
        must_change_password=bool(getattr(user, "must_change_password", False)),
    )
    await db_session.close()
    return result


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _redirect_uri_allowed(redirect: str) -> bool:
    configured = (settings.oidc_redirect_uri or "").strip()
    if configured and secrets.compare_digest(redirect, configured):
        return True
    return any(redirect.startswith(prefix) for prefix in ALLOWED_OIDC_REDIRECT_PREFIXES)


@router.get("/sso/login")
async def sso_login(
    redirect_uri: Optional[str] = None,
    tenant_subdomain: Optional[str] = None,
):
    """
    Initiate OIDC/SSO login with state + PKCE.

    tenant_subdomain is required so the callback can bind the IdP identity
    to exactly one tenant (never scan all tenants).
    """
    if not settings.oidc_issuer or not settings.oidc_client_id:
        raise HTTPException(
            status_code=500,
            detail="OIDC not configured (OIDC_ISSUER and OIDC_CLIENT_ID required)",
        )
    if not tenant_subdomain:
        raise HTTPException(status_code=400, detail="tenant_subdomain required")

    from sqlalchemy import select
    from app.models.tenant import Tenant
    from app.storage.control_plane_db import ControlPlaneSessionLocal

    async with ControlPlaneSessionLocal() as control_session:
        stmt = select(Tenant).where(Tenant.subdomain == tenant_subdomain)
        result = await control_session.execute(stmt)
        tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    redirect = redirect_uri or settings.oidc_redirect_uri
    if not redirect or not _redirect_uri_allowed(redirect):
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _pkce_challenge(code_verifier)
    await redis_client.set_json(
        OIDC_STATE_PARTITION,
        f"oidc_state:{state}",
        {
            "code_verifier": code_verifier,
            "redirect_uri": redirect,
            "tenant_id": str(tenant.tenant_id),
            "tenant_subdomain": tenant_subdomain,
        },
        ex=600,
    )

    params = {
        "client_id": settings.oidc_client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{settings.oidc_issuer.rstrip('/')}/authorize?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


def _id_token_claims(id_token: str) -> dict:
    claims = pyjwt.decode(id_token, options={"verify_signature": False})
    issuer = (settings.oidc_issuer or "").rstrip("/")
    token_iss = str(claims.get("iss") or "").rstrip("/")
    if not issuer or token_iss != issuer:
        raise HTTPException(status_code=401, detail="Invalid identity token issuer")
    aud = claims.get("aud")
    client_id = settings.oidc_client_id
    aud_ok = aud == client_id or (isinstance(aud, list) and client_id in aud)
    if not aud_ok:
        raise HTTPException(status_code=401, detail="Invalid identity token audience")
    exp = claims.get("exp")
    if exp is not None:
        try:
            if int(exp) < int(datetime.now(timezone.utc).timestamp()):
                raise HTTPException(status_code=401, detail="Identity token expired")
        except HTTPException:
            raise
        except (TypeError, ValueError):
            raise HTTPException(status_code=401, detail="Invalid identity token")
    return claims


@router.get("/sso/callback")
async def sso_callback(
    code: str = Query(..., description="Authorization code from OIDC provider"),
    state: Optional[str] = Query(None),
):
    """
    Handle OIDC/SSO callback and issue SnyQ JWTs only.

    IdP access/refresh tokens never leave the server.
    """
    if not settings.oidc_issuer or not settings.oidc_client_id or not settings.oidc_client_secret:
        raise HTTPException(status_code=500, detail="OIDC not configured")
    if not state:
        raise HTTPException(status_code=400, detail="state required")

    state_data = await redis_client.get_json(OIDC_STATE_PARTITION, f"oidc_state:{state}")
    await redis_client.delete(OIDC_STATE_PARTITION, f"oidc_state:{state}")
    if not state_data:
        raise HTTPException(status_code=401, detail="Invalid or expired state")

    redirect = state_data.get("redirect_uri") or settings.oidc_redirect_uri
    code_verifier = state_data.get("code_verifier")
    tenant_id = state_data.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="OIDC state missing tenant")

    token_url = f"{settings.oidc_issuer.rstrip('/')}/token"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
                "code_verifier": code_verifier,
            },
        )

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

    idp_payload = response.json()
    id_token = idp_payload.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="OIDC response missing id_token")

    claims = _id_token_claims(id_token)
    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Identity token missing email")

    try:
        routing = await tenant_resolver.resolve(str(tenant_id))
    except Exception:
        raise HTTPException(status_code=401, detail="SSO login failed")

    from sqlalchemy import select
    from app.models.user import User

    factory = tenant_db_manager.get_session_factory(
        routing.db_host,
        routing.db_name,
        routing.db_user,
        routing.db_password,
        str(tenant_id),
    )
    db_session = factory()
    try:
        result = await db_session.execute(
            select(User).where(
                User.email == email,
                User.tenant_id == UUID(str(tenant_id)),
                User.is_active == True,  # noqa: E712
            )
        )
        user = result.scalar_one_or_none()
        if user is None or user.status != "active":
            raise HTTPException(status_code=401, detail="SSO login failed")

        role = getattr(user, "role", None) or "member"
        scopes = scopes_for_role(role)
        access_token = await token_service.issue_access_token(
            tenant_id=str(tenant_id),
            principal_id=str(user.principal_id),
            scopes=scopes,
            role=role,
            token_version=getattr(user, "token_version", 0) or 0,
        )
        refresh_token = await token_service.issue_refresh_token(
            tenant_id=str(tenant_id),
            principal_id=str(user.principal_id),
        )
        result = SsoLoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.token_ttl_access,
            role=role,
        )
    finally:
        await db_session.close()
    return result
