"""SharePoint connector HTTP surface.

Mounted at /connectors and /api/v1/connectors alongside the Google router.
Org path is admin-managed client credentials (service principal).
Personal path is delegated Microsoft Graph OAuth.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import get_current_user, get_tenant, require_admin, require_scope
from app.connectors.google import status_store
from app.connectors.google.oauth_state import (
    decode_oauth_state,
    encode_oauth_state,
)
from app.connectors.sharepoint.credentials import (
    cache_app_secret,
    is_dev_fixture,
    mint_client_credentials_token,
    parse_app_secret,
    DEV_FIXTURE_APP_SECRET,
    DEV_FIXTURE_VAULT_KEY,
)
from app.connectors.google.keys import cursor_scope_id
from app.connectors.sharepoint.keys import sharepoint_oauth_token_key
from app.connectors.sharepoint.oauth import (
    microsoft_account_signals,
    missing_scopes_block_connect,
    sharepoint_oauth_from_settings,
)
from app.connectors.sharepoint.token_store import (
    PersistentSharePointTokenStore,
    sharepoint_credential_ref,
)
from app.core.config import settings
from app.services.cursor_store import cursor_store
from app.services.tenant_resolver import TenantRouting
from app.workers.tasks import backfill_source, backfill_tenant_source

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connectors", tags=["connectors-sharepoint"])

SHAREPOINT_SOURCE = "sharepoint"
_DEFAULT_CALLBACK = "http://localhost:8000/connectors/sharepoint/callback"


def _redirect_uri() -> str:
    return (settings.microsoft_sharepoint_redirect_uri or _DEFAULT_CALLBACK).rstrip("/")


def _user_id(current_user: Dict[str, Any]) -> str:
    return str(current_user.get("sub") or current_user.get("principal_id") or "")


def _jti(current_user: Dict[str, Any]) -> str:
    return str(current_user.get("jti") or "")


def _user_email(current_user: Dict[str, Any]) -> str:
    return str(current_user.get("email") or current_user.get("preferred_username") or "")


def _frontend_redirect(status: str, error: Optional[str] = None) -> str:
    from urllib.parse import quote

    base = (getattr(settings, "frontend_url", None) or "http://localhost:3000").rstrip("/")
    url = f"{base}/connectors?sharepoint={quote(status)}"
    if error:
        url += f"&error={quote(error)}"
    return url


class OrganizationConnectRequest(BaseModel):
    vault_key: str = Field(..., description="Vault key containing Graph app credentials JSON")
    site_url: Optional[str] = Field(
        default=None,
        description="Optional site URL. Blank = all sites the app can read.",
    )


class OrganizationToggleRequest(BaseModel):
    enabled: bool


def _tenant_session_factory(tenant_id: str):
    from app.services.tenant_resolver import tenant_resolver
    from app.storage.tenant_db import tenant_db_manager

    async def _inner():
        routing = await tenant_resolver.resolve(tenant_id)
        factory = tenant_db_manager.get_session_factory(
            routing.db_host,
            routing.db_name,
            routing.db_user,
            routing.db_password,
            str(routing.tenant_id),
        )
        return factory, routing

    return _inner


@router.post(
    "/admin/sharepoint/organization/connect",
    summary="Connect organization SharePoint service principal",
    dependencies=[Depends(require_scope("connectors.write")), Depends(require_admin)],
)
async def connect_organization_sharepoint(
    request: OrganizationConnectRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    from app.models.tenant_connector import TenantConnector
    from app.storage.vault_client import vault_client

    try:
        raw = await vault_client.get_secret(request.vault_key)
        info = parse_app_secret(raw)
    except Exception as exc:
        from app.core.backends import mock_backends_allowed

        if mock_backends_allowed() and request.vault_key.strip() == DEV_FIXTURE_VAULT_KEY:
            await vault_client.set_secret(request.vault_key, json.dumps(DEV_FIXTURE_APP_SECRET))
            info = dict(DEV_FIXTURE_APP_SECRET)
            logger.info("Installed SharePoint DEV_FIXTURE vault secret in-process")
        else:
            logger.exception("SharePoint vault validation failed")
            raise HTTPException(status_code=400, detail=f"Invalid vault secret: {exc}") from exc

    try:
        await mint_client_credentials_token(info)
    except HTTPException:
        raise
    except Exception as exc:
        if is_dev_fixture(info):
            logger.info("SharePoint connect using DEV_FIXTURE credentials")
        else:
            logger.exception("SharePoint token mint failed")
            raise HTTPException(
                status_code=400,
                detail=f"Could not obtain a Graph token with those credentials: {exc}",
            ) from exc

    cache_app_secret(str(tenant_id), info)

    tenant_uuid = UUID(str(tenant_id))
    actor_uuid = UUID(_user_id(current_user) or str(tenant_id))
    site_url = (request.site_url or "").strip()
    admin_email = _user_email(current_user)

    opener = _tenant_session_factory(str(tenant_id))
    factory, _routing = await opener()
    async with factory() as session:
        from app.models.user import User

        if not admin_email:
            user_row = await session.execute(
                select(User).where(User.principal_id == actor_uuid)
            )
            found = user_row.scalar_one_or_none()
            if found and found.email:
                admin_email = found.email
        config = {
            "credential_mode": "client_credentials",
            "connected_by": _user_id(current_user),
            "connected_by_email": admin_email,
            "dev_fixture": is_dev_fixture(info),
        }
        if site_url:
            config["site_url"] = site_url

        result = await session.execute(
            select(TenantConnector).where(
                TenantConnector.tenant_id == tenant_uuid,
                TenantConnector.source_type == SHAREPOINT_SOURCE,
                TenantConnector.connection_scope == "organization",
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            session.add(
                TenantConnector(
                    tenant_id=tenant_uuid,
                    source_type=SHAREPOINT_SOURCE,
                    connection_scope="organization",
                    enabled=True,
                    config=config,
                    setup_by=actor_uuid,
                    credential_ref=request.vault_key,
                )
            )
        else:
            row.enabled = True
            row.config = config
            row.credential_ref = request.vault_key
            row.setup_by = actor_uuid
        await session.commit()

    status_store.set_status(
        str(tenant_id),
        SHAREPOINT_SOURCE,
        user_id="organization",
        connection_status="active" if is_dev_fixture(info) else "active",
        last_error="",
    )
    return {
        "status": "connected",
        "tenant_id": tenant_id,
        "vault_key": request.vault_key,
        "dev_fixture": is_dev_fixture(info),
    }


@router.post(
    "/admin/sharepoint/organization/disconnect",
    summary="Disconnect organization SharePoint connector",
    dependencies=[Depends(require_scope("connectors.write")), Depends(require_admin)],
)
async def disconnect_organization_sharepoint(
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    from app.models.tenant_connector import TenantConnector

    tenant_uuid = UUID(str(tenant_id))
    opener = _tenant_session_factory(str(tenant_id))
    factory, _routing = await opener()
    async with factory() as session:
        result = await session.execute(
            select(TenantConnector).where(
                TenantConnector.tenant_id == tenant_uuid,
                TenantConnector.source_type == SHAREPOINT_SOURCE,
                TenantConnector.connection_scope == "organization",
            )
        )
        row = result.scalar_one_or_none()
        if row:
            await session.delete(row)
            await session.commit()

    status_store.set_status(
        str(tenant_id),
        SHAREPOINT_SOURCE,
        user_id="organization",
        connection_status="not_connected",
        files_indexed=0,
        last_error="",
    )
    return {"status": "disconnected", "tenant_id": tenant_id}


@router.post(
    "/admin/sharepoint/organization/toggle",
    summary="Enable or disable organization SharePoint for members",
    dependencies=[Depends(require_scope("connectors.write")), Depends(require_admin)],
)
async def toggle_organization_sharepoint(
    request: OrganizationToggleRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    from app.models.tenant import Tenant
    from app.storage.control_plane_db import ControlPlaneSessionLocal

    tenant_uuid = UUID(str(tenant_id))
    async with ControlPlaneSessionLocal() as session:
        result = await session.execute(select(Tenant).where(Tenant.tenant_id == tenant_uuid))
        tenant_row = result.scalar_one_or_none()
        if tenant_row is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant_row.sharepoint_org_enabled = request.enabled
        await session.commit()
    return {"status": "toggled", "tenant_id": tenant_id, "enabled": request.enabled}


@router.post(
    "/admin/sharepoint/organization/backfill",
    summary="Trigger organization SharePoint backfill",
    dependencies=[Depends(require_scope("connectors.write")), Depends(require_admin)],
)
async def trigger_organization_sharepoint_backfill(
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    from app.connectors.google.keys import cursor_scope_id
    from app.models.tenant_connector import TenantConnector

    opener = _tenant_session_factory(str(tenant_id))
    factory, _routing = await opener()
    admin_id = ""
    async with factory() as session:
        result = await session.execute(
            select(TenantConnector).where(
                TenantConnector.tenant_id == UUID(str(tenant_id)),
                TenantConnector.source_type == SHAREPOINT_SOURCE,
                TenantConnector.connection_scope == "organization",
            )
        )
        row = result.scalar_one_or_none()
        if row:
            admin_id = str((row.config or {}).get("connected_by") or "")

    for scope in (
        f"{tenant_id}_organization",
        cursor_scope_id(str(tenant_id), "organization"),
        cursor_scope_id(str(tenant_id), admin_id) if admin_id else "",
    ):
        if scope:
            await cursor_store.update_cursor(scope, SHAREPOINT_SOURCE, "")

    status_store.set_status(
        str(tenant_id),
        SHAREPOINT_SOURCE,
        user_id="organization",
        connection_status="syncing",
        last_error="",
    )
    task_result = backfill_tenant_source.delay(
        tenant_id=str(tenant_id),
        source_type=SHAREPOINT_SOURCE,
        user_id="organization",
    )
    return {
        "status": "queued",
        "task_id": task_result.id,
        "tenant_id": tenant_id,
        "source_type": SHAREPOINT_SOURCE,
    }


@router.get(
    "/sharepoint/organization/status",
    summary="Get organization SharePoint connector status",
    dependencies=[Depends(require_scope("connectors.read"))],
)
async def get_organization_sharepoint_status(
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    from app.models.tenant import Tenant
    from app.models.tenant_connector import TenantConnector
    from app.storage.control_plane_db import ControlPlaneSessionLocal

    tenant_uuid = UUID(str(tenant_id))
    async with ControlPlaneSessionLocal() as cp_session:
        tenant_result = await cp_session.execute(select(Tenant).where(Tenant.tenant_id == tenant_uuid))
        tenant_row = tenant_result.scalar_one_or_none()
        org_enabled = bool(getattr(tenant_row, "sharepoint_org_enabled", False)) if tenant_row else False

    opener = _tenant_session_factory(str(tenant_id))
    factory, _routing = await opener()
    async with factory() as session:
        result = await session.execute(
            select(TenantConnector).where(
                TenantConnector.tenant_id == tenant_uuid,
                TenantConnector.source_type == SHAREPOINT_SOURCE,
                TenantConnector.connection_scope == "organization",
            )
        )
        row = result.scalar_one_or_none()

    runtime = status_store.get_status(str(tenant_id), SHAREPOINT_SOURCE, user_id="organization")
    connection_status = runtime.get("connection_status") or "not_connected"
    is_valid = False
    if row is not None:
        mode = str((row.config or {}).get("credential_mode") or "")
        is_valid = mode == "client_credentials" and bool(row.credential_ref)

    if not is_valid:
        connection_status = "not_connected"
        runtime["files_indexed"] = 0
        runtime["last_sync_at"] = None
        runtime["last_error"] = None
    elif connection_status == "not_connected" and org_enabled:
        scope_id = f"{tenant_id}_organization"
        cursor = await cursor_store.get_cursor(scope_id, SHAREPOINT_SOURCE)
        if cursor:
            connection_status = "active"

    scope_id = f"{tenant_id}_organization"
    cursor = await cursor_store.get_cursor(scope_id, SHAREPOINT_SOURCE)
    return {
        "tenant_id": tenant_id,
        "source_type": SHAREPOINT_SOURCE,
        "cursor": cursor,
        "watch_active": False,
        "details": {
            "connection_status": connection_status,
            "files_indexed": runtime.get("files_indexed") or 0,
            "last_sync_at": runtime.get("last_sync_at"),
            "last_error": runtime.get("last_error"),
            "org_enabled": org_enabled,
            "connected": is_valid,
            "dev_fixture": bool((row.config or {}).get("dev_fixture")) if row else False,
        },
    }


@router.get(
    "/sharepoint/authorize",
    summary="Generate Microsoft Graph OAuth URL for personal SharePoint",
    dependencies=[Depends(require_scope("connectors.write"))],
)
async def get_sharepoint_authorize_url(
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
    response: Response = None,
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != str(tenant_id):
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")
    client_id = settings.microsoft_sharepoint_client_id or ""
    if not client_id:
        raise HTTPException(status_code=503, detail="MICROSOFT_SHAREPOINT_CLIENT_ID is not configured")

    binding_token = secrets.token_urlsafe(32)
    user_id = _user_id(current_user)
    state = encode_oauth_state(
        str(tenant_id), user_id, "personal", jti=_jti(current_user), binding_token=binding_token
    )
    token_store = PersistentSharePointTokenStore(str(tenant_id))
    oauth = sharepoint_oauth_from_settings(token_store, principal_id=user_id, connection_scope="personal")
    auth_url = oauth.build_authorization_url(str(tenant_id), _redirect_uri(), state=state)
    cookie_secure = _redirect_uri().startswith("https://")
    response.set_cookie(
        key="oauth_binding",
        value=binding_token,
        max_age=600,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
    )
    return {
        "authorization_url": auth_url,
        "tenant_id": tenant_id,
        "connection_scope": "personal",
    }


@router.get(
    "/sharepoint/callback",
    summary="Microsoft Graph OAuth callback for SharePoint",
)
async def sharepoint_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    if error:
        return RedirectResponse(_frontend_redirect("error", error), status_code=302)
    if not code or not state:
        return RedirectResponse(_frontend_redirect("error", "missing_code_or_state"), status_code=302)

    binding_cookie = request.cookies.get("oauth_binding")
    if not binding_cookie:
        return RedirectResponse(_frontend_redirect("error", "missing_binding_cookie"), status_code=302)

    payload = decode_oauth_state(state, require_binding_token=binding_cookie)
    if not payload:
        return RedirectResponse(_frontend_redirect("error", "invalid_state"), status_code=302)

    tenant_id = str(payload["tenant_id"])
    user_id = str(payload["user_id"])
    connection_scope = str(payload.get("connection_scope") or "personal")
    token_store = PersistentSharePointTokenStore(tenant_id)
    oauth = sharepoint_oauth_from_settings(token_store, principal_id=user_id, connection_scope=connection_scope)
    try:
        token_data = await oauth.exchange_code_for_tokens(tenant_id, code, _redirect_uri())
        access = str(token_data.get("access_token") or "")
        me_profile = await oauth.get_me_profile(access) if access else {}
        mailbox_email = str(me_profile.get("mail") or me_profile.get("userPrincipalName") or "")
        signals = microsoft_account_signals(token_data, me_profile)
        logger.info(
            "SharePoint account signals tid=%s idp=%s jwt_source=%s me_id_len=%s me_id_is_guid=%s issuers=%s",
            signals.get("tid") or "(none)",
            signals.get("idp") or "(none)",
            signals.get("jwt_source") or "(none)",
            len(str(signals.get("me_id") or "")),
            signals.get("me_id_is_guid"),
            signals.get("identity_issuers") or [],
        )
        missing = list(token_data.get("_missing_scopes") or [])
        if missing_scopes_block_connect(token_data, me_profile=me_profile):
            logger.error(
                "SharePoint granted scope missing requested permissions missing=%s tid=%s",
                missing,
                signals.get("tid") or "(none)",
            )
            return RedirectResponse(
                _frontend_redirect("error", "granted_scope_incomplete"),
                status_code=302,
            )
        if missing == ["Sites.Read.All"]:
            logger.warning(
                "SharePoint granted scope omitted Sites.Read.All on personal MSA tid=%s; continuing OneDrive-only",
                signals.get("tid") or "(none)",
            )
    except Exception:
        logger.exception("SharePoint OAuth token exchange failed")
        return RedirectResponse(_frontend_redirect("error", "token_exchange_failed"), status_code=302)

    merged = dict(token_data or {})
    if mailbox_email:
        merged["mailbox_email"] = mailbox_email
    merged["connected_by"] = user_id
    token_store.set_token(sharepoint_oauth_token_key(tenant_id, user_id, connection_scope), merged)

    await _record_personal_connector_row(tenant_id, user_id, mailbox_email)
    # Reconnect may switch Microsoft accounts; the previous drive delta cursor
    # must not resume or the new OneDrive is skipped.
    await cursor_store.update_cursor(
        cursor_scope_id(tenant_id, user_id), SHAREPOINT_SOURCE, ""
    )
    status_store.set_status(
        tenant_id,
        SHAREPOINT_SOURCE,
        user_id=user_id,
        connection_status="syncing",
        files_indexed=0,
        last_error="",
    )
    try:
        backfill_source.delay(
            tenant_id=tenant_id,
            source_type=SHAREPOINT_SOURCE,
            user_id=user_id,
            connector_id=sharepoint_credential_ref(tenant_id, user_id, connection_scope),
        )
    except Exception:
        logger.exception("Failed to enqueue SharePoint backfill")
        status_store.set_status(
            tenant_id,
            SHAREPOINT_SOURCE,
            user_id=user_id,
            connection_status="error",
            last_error="celery_enqueue_failed",
        )
    return RedirectResponse(_frontend_redirect("connected"), status_code=302)


async def _record_personal_connector_row(tenant_id: str, user_id: str, mailbox_email: str) -> None:
    try:
        tenant_uuid = UUID(tenant_id)
        actor_uuid = UUID(user_id) if user_id else tenant_uuid
    except (TypeError, ValueError):
        return
    try:
        from app.models.tenant_connector import TenantConnector

        opener = _tenant_session_factory(tenant_id)
        factory, _routing = await opener()
        cred_ref = sharepoint_credential_ref(tenant_id, user_id, "personal")
        async with factory() as session:
            result = await session.execute(
                select(TenantConnector).where(
                    TenantConnector.tenant_id == tenant_uuid,
                    TenantConnector.source_type == SHAREPOINT_SOURCE,
                    TenantConnector.connection_scope == "personal",
                )
            )
            row = result.scalar_one_or_none()
            config = {
                "credential_mode": "oauth",
                "mailbox_email": mailbox_email,
                "connected_by": user_id,
                "connected_by_email": mailbox_email,
            }
            if row is None:
                session.add(
                    TenantConnector(
                        tenant_id=tenant_uuid,
                        source_type=SHAREPOINT_SOURCE,
                        connection_scope="personal",
                        enabled=True,
                        config=config,
                        setup_by=actor_uuid,
                        credential_ref=cred_ref,
                    )
                )
            else:
                row.enabled = True
                merged = dict(row.config or {})
                merged.update(config)
                row.config = merged
                row.credential_ref = cred_ref
                row.setup_by = actor_uuid
            await session.commit()
    except Exception:
        logger.exception("Failed to record personal SharePoint connector row")
