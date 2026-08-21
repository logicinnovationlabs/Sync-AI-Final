"""
Connector HTTP surface — lives with the connector package, not under /api/v1.

Endpoints:
- POST /connectors/{source_type}/backfill: Trigger backfill for tenant
- GET  /connectors/{source_type}/status:   Get sync status & watches
- POST /connectors/{source_type}/disconnect: Disconnect source & revoke watches
- GET  /connectors/google/authorize:      Generate Google OAuth URL
- GET  /connectors/google/callback:       OAuth callback (no JWT; state-bound)
"""

from typing import Dict, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
import logging

from app.api.deps import get_current_user, get_tenant, require_scope
from app.services.tenant_resolver import TenantRouting
from app.workers.tasks import backfill_source, backfill_tenant_source
from app.services.cursor_store import cursor_store
from app.core.config import settings
from app.connectors.google.oauth import google_oauth_from_settings
from app.connectors.google.keys import (
    cursor_scope_id,
    google_oauth_token_key,
)
from app.connectors.google.oauth_state import (
    decode_oauth_state,
    encode_oauth_state,
    frontend_connectors_redirect,
)
from app.connectors.google.token_store import (
    PersistentGoogleTokenStore,
    google_credential_ref,
)
from app.connectors.google import status_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connectors", tags=["connectors"])

GOOGLE_SOURCES = ("google_drive", "google_gmail")
_DEFAULT_GOOGLE_CALLBACK = "http://localhost:8000/connectors/google/callback"


def _google_redirect_uri() -> str:
    """Must match the URI registered on the Google OAuth client exactly."""
    return (settings.google_redirect_uri or _DEFAULT_GOOGLE_CALLBACK).rstrip("/")


class BackfillRequest(BaseModel):
    """Backfill request payload."""
    source_type: Optional[str] = Field(None, description="Connector source type (e.g. google_drive, google_gmail)")


class ConnectorStatusResponse(BaseModel):
    """Connector status response payload."""
    tenant_id: str
    source_type: str
    cursor: Optional[str]
    watch_active: bool
    details: Dict[str, Any]


def _user_id(current_user: Dict[str, Any]) -> str:
    return str(current_user.get("sub") or current_user.get("principal_id") or "")


@router.post(
    "/{source_type}/backfill",
    summary="Trigger connector backfill",
    dependencies=[Depends(require_scope("connectors.write"))],
)
async def trigger_backfill(
    source_type: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    """
    Initiate asynchronous backfill for a connector source.

    Requires:
    - Valid JWT Access Token (A1)
    - Scope: connectors.write (A5)
    - Tenant Isolation: Operates ONLY on the tenant_id in the JWT payload (A4)
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    user_id = _user_id(current_user)
    status_store.set_status(
        tenant_id, source_type, user_id=user_id, connection_status="syncing", last_error=""
    )
    task_result = backfill_tenant_source.delay(
        tenant_id=tenant_id,
        source_type=source_type,
        user_id=user_id,
    )

    return {
        "status": "queued",
        "task_id": task_result.id,
        "tenant_id": tenant_id,
        "source_type": source_type,
    }


@router.get(
    "/{source_type}/status",
    summary="Get connector sync status",
    response_model=ConnectorStatusResponse,
    dependencies=[Depends(require_scope("connectors.read"))],
)
async def get_connector_status(
    source_type: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    """
    Retrieve sync cursor, watch flag, and runtime connection status.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    user_id = _user_id(current_user)
    scope_id = cursor_scope_id(tenant_id, user_id)
    cursor = await cursor_store.get_cursor(scope_id, source_type)

    watch_info = None
    try:
        if source_type == "google_drive":
            watch_info = await cursor_store.get_watch_by_channel(
                f"drive-{scope_id}", "resource"
            )
        elif source_type == "google_gmail":
            watch_info = await cursor_store.get_watch_by_email(
                f"user@{scope_id}.com", source_type
            )
    except Exception:
        watch_info = None

    runtime = status_store.get_status(tenant_id, source_type, user_id=user_id)
    token_store = PersistentGoogleTokenStore(tenant_id)
    has_token = token_store.get_token(google_oauth_token_key(tenant_id, user_id)) is not None
    if not has_token:
        has_token = token_store.get_token(google_oauth_token_key(tenant_id)) is not None
    connection_status = runtime.get("connection_status") or "not_connected"
    if connection_status == "not_connected" and (cursor or has_token):
        connection_status = "active" if cursor else "syncing"

    details: Dict[str, Any] = {
        "connection_status": connection_status,
        "files_indexed": runtime.get("files_indexed") or 0,
        "last_sync_at": runtime.get("last_sync_at"),
        "last_error": runtime.get("last_error"),
        "token_present": has_token,
    }
    if watch_info:
        details["watch_info"] = watch_info

    return ConnectorStatusResponse(
        tenant_id=tenant_id,
        source_type=source_type,
        cursor=cursor,
        watch_active=watch_info is not None,
        details=details,
    )


@router.post(
    "/{source_type}/disconnect",
    summary="Disconnect connector and revoke watches",
    dependencies=[Depends(require_scope("connectors.write"))],
)
async def disconnect_connector(
    source_type: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    user_id = _user_id(current_user)
    await cursor_store.update_cursor(cursor_scope_id(tenant_id, user_id), source_type, "")
    status_store.set_status(
        tenant_id,
        source_type,
        user_id=user_id,
        connection_status="not_connected",
        files_indexed=0,
        last_error="",
    )

    return {
        "status": "disconnected",
        "tenant_id": tenant_id,
        "source_type": source_type,
    }


@router.get(
    "/google/authorize",
    summary="Generate Google OAuth authorization URL",
    dependencies=[Depends(require_scope("connectors.write"))],
)
async def get_google_authorize_url(
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    """
    Generate Google OAuth authorization link for the authenticated tenant.

    State carries tenant_id + user_id (base64 JSON) plus a CSRF nonce.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != str(tenant_id):
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    client_id = settings.google_client_id or ""
    if not client_id:
        raise HTTPException(status_code=503, detail="GOOGLE_CLIENT_ID is not configured")

    redirect_uri = _google_redirect_uri()
    user_id = _user_id(current_user)
    state = encode_oauth_state(str(tenant_id), user_id)
    token_store = PersistentGoogleTokenStore(str(tenant_id))
    oauth = google_oauth_from_settings(token_store, principal_id=user_id)
    auth_url = oauth.build_authorization_url(str(tenant_id), redirect_uri, state=state)

    return {
        "authorization_url": auth_url,
        "tenant_id": tenant_id,
    }


@router.get(
    "/google/callback",
    summary="Google OAuth callback — exchange code, store tokens, auto-sync",
)
async def google_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """
    Unauthenticated by design: Google redirects the browser here without our JWT.
    Binding is the CSRF state nonce issued by /google/authorize.
    On success: encrypt+store tokens, enqueue Drive + Gmail full backfill, redirect UI.
    """
    if error:
        return RedirectResponse(frontend_connectors_redirect("error", error), status_code=302)
    if not code or not state:
        return RedirectResponse(
            frontend_connectors_redirect("error", "missing_code_or_state"),
            status_code=302,
        )

    payload = decode_oauth_state(state)
    if not payload:
        return RedirectResponse(
            frontend_connectors_redirect("error", "invalid_state"),
            status_code=302,
        )

    tenant_id = str(payload["tenant_id"])
    user_id = str(payload["user_id"])
    redirect_uri = _google_redirect_uri()

    token_store = PersistentGoogleTokenStore(tenant_id)
    oauth = google_oauth_from_settings(token_store, principal_id=user_id)
    try:
        token_data = await oauth.exchange_code_for_tokens(tenant_id, code, redirect_uri)
    except Exception:
        return RedirectResponse(
            frontend_connectors_redirect("error", "token_exchange_failed"),
            status_code=302,
        )

    mailbox_email = await _resolve_mailbox_email(oauth, tenant_id)
    if mailbox_email:
        merged = dict(token_data or {})
        merged["mailbox_email"] = mailbox_email
        token_store.set_token(google_oauth_token_key(tenant_id, user_id), merged)
    await _record_connector_rows(tenant_id, user_id, mailbox_email)

    for source_type in GOOGLE_SOURCES:
        status_store.set_status(
            tenant_id,
            source_type,
            user_id=user_id,
            connection_status="syncing",
            last_error="",
        )
        try:
            backfill_source.delay(
                tenant_id=tenant_id,
                source_type=source_type,
                user_id=user_id,
                connector_id=google_credential_ref(tenant_id, user_id),
            )
        except Exception:
            status_store.set_status(
                tenant_id,
                source_type,
                user_id=user_id,
                connection_status="error",
                last_error="celery_enqueue_failed",
            )
            logger.exception(
                "Failed to enqueue backfill tenant=%s source=%s", tenant_id, source_type
            )

    return RedirectResponse(frontend_connectors_redirect("connected"), status_code=302)


async def _resolve_mailbox_email(oauth, tenant_id: str) -> str:
    try:
        token = await oauth.get_valid_token(tenant_id)
        from app.connectors.google.clients.gmail_client import GmailClient

        profile = await GmailClient().get_profile(token)
        return str(profile.get("emailAddress") or "")
    except Exception:
        return ""


async def _record_connector_rows(tenant_id: str, user_id: str, mailbox_email: str) -> None:
    """Best-effort TenantConnector upsert; vault key name only, never the token blob."""
    try:
        tenant_uuid = UUID(tenant_id)
        actor_uuid = UUID(user_id) if user_id else tenant_uuid
    except (TypeError, ValueError):
        return

    try:
        from app.services.tenant_resolver import tenant_resolver
        from app.storage.tenant_db import tenant_db_manager
        from app.models.tenant_connector import TenantConnector

        routing = await tenant_resolver.resolve(tenant_id)
        factory = tenant_db_manager.get_session_factory(
            routing.db_host,
            routing.db_name,
            routing.db_user,
            routing.db_password,
            str(routing.tenant_id),
        )
        cred_ref = google_credential_ref(tenant_id, user_id)
        async with factory() as session:
            for source_type in GOOGLE_SOURCES:
                result = await session.execute(
                    select(TenantConnector).where(
                        TenantConnector.tenant_id == tenant_uuid,
                        TenantConnector.source_type == source_type,
                    )
                )
                row = result.scalar_one_or_none()
                config = {"mailbox_email": mailbox_email, "connected_by": user_id}
                if row is None:
                    session.add(
                        TenantConnector(
                            tenant_id=tenant_uuid,
                            source_type=source_type,
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
        return
