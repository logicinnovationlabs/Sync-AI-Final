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

from app.api.deps import get_current_user, get_tenant, require_scope, require_admin
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
from app.connectors import provider_registry

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


class OrganizationConnectRequest(BaseModel):
    """Organization Google Workspace connector connection request."""
    vault_key: str = Field(..., description="Vault key containing service account credentials")
    impersonate_email: str = Field(..., description="Email to impersonate for domain-wide delegation")


class OrganizationToggleRequest(BaseModel):
    """Organization Google Workspace connector toggle request."""
    enabled: bool = Field(..., description="Whether the connector is enabled for the tenant")


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
        tenant_id, source_type, user_id=user_id, connection_status="syncing", last_error="",
        force=True,
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


@router.post(
    "/admin/google/organization/connect",
    summary="Connect organization Google Workspace service account",
    dependencies=[Depends(require_scope("connectors.write")), Depends(require_admin)],
)
async def connect_organization_connector(
    request: OrganizationConnectRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    """
    Connect organization Google Workspace connector using a service account.

    Admin-only endpoint. Stores the service account credential reference in Vault
    and creates organization-scoped TenantConnector rows.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    try:
        from app.services.tenant_resolver import tenant_resolver
        from app.storage.tenant_db import tenant_db_manager
        from app.storage.vault_client import vault_client
        from app.models.tenant_connector import TenantConnector

        tenant_uuid = UUID(tenant_id)
        actor_uuid = UUID(current_user.get("sub") or current_user.get("principal_id") or tenant_id)

        # Verify the vault key exists and contains valid service account JSON
        try:
            raw = await vault_client.get_secret(request.vault_key)
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            import json
            info = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(info, dict):
                raise HTTPException(status_code=400, detail="Vault secret is not a valid JSON object")
            # Validate it's a service account key (has project_id, private_key, etc.)
            if not all(k in info for k in ["project_id", "private_key_id", "private_key"]):
                raise HTTPException(status_code=400, detail="Vault secret is not a valid service account JSON")
        except Exception as e:
            logger.exception("Vault validation failed for organization connector")
            raise HTTPException(status_code=400, detail=f"Invalid vault secret: {str(e)}")

        routing = await tenant_resolver.resolve(tenant_id)
        factory = tenant_db_manager.get_session_factory(
            routing.db_host,
            routing.db_name,
            routing.db_user,
            routing.db_password,
            str(routing.tenant_id),
        )

        async with factory() as session:
            for source_type in GOOGLE_SOURCES:
                result = await session.execute(
                    select(TenantConnector).where(
                        TenantConnector.tenant_id == tenant_uuid,
                        TenantConnector.source_type == source_type,
                        TenantConnector.connection_scope == "organization",
                    )
                )
                row = result.scalar_one_or_none()
                config = {
                    "credential_mode": "service_account_dwd",
                    "impersonate_user_email": request.impersonate_email,
                }
                if row is None:
                    session.add(
                        TenantConnector(
                            tenant_id=tenant_uuid,
                            source_type=source_type,
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

        return {
            "status": "connected",
            "tenant_id": tenant_id,
            "vault_key": request.vault_key,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Organization connector connection failed")
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")


@router.post(
    "/admin/google/organization/disconnect",
    summary="Disconnect organization Google Workspace connector",
    dependencies=[Depends(require_scope("connectors.write")), Depends(require_admin)],
)
async def disconnect_organization_connector(
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    """
    Disconnect organization Google Workspace connector.

    Admin-only endpoint. Removes organization-scoped TenantConnector rows.
    Does not delete the service account from Vault.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    try:
        from app.services.tenant_resolver import tenant_resolver
        from app.storage.tenant_db import tenant_db_manager
        from app.models.tenant_connector import TenantConnector

        tenant_uuid = UUID(tenant_id)

        routing = await tenant_resolver.resolve(tenant_id)
        factory = tenant_db_manager.get_session_factory(
            routing.db_host,
            routing.db_name,
            routing.db_user,
            routing.db_password,
            str(routing.tenant_id),
        )

        async with factory() as session:
            for source_type in GOOGLE_SOURCES:
                result = await session.execute(
                    select(TenantConnector).where(
                        TenantConnector.tenant_id == tenant_uuid,
                        TenantConnector.source_type == source_type,
                        TenantConnector.connection_scope == "organization",
                    )
                )
                row = result.scalar_one_or_none()
                if row:
                    await session.delete(row)
            await session.commit()

        for source_type in GOOGLE_SOURCES:
            status_store.clear_status(
                tenant_id, source_type, user_id="organization"
            )

        return {
            "status": "disconnected",
            "tenant_id": tenant_id,
        }
    except Exception as e:
        logger.exception("Organization connector disconnection failed")
        raise HTTPException(status_code=500, detail=f"Disconnection failed: {str(e)}")


@router.post(
    "/admin/google/organization/toggle",
    summary="Enable or disable organization Google Workspace connector",
    dependencies=[Depends(require_scope("connectors.write")), Depends(require_admin)],
)
async def toggle_organization_connector(
    request: OrganizationToggleRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    """
    Enable or disable organization Google Workspace connector for the tenant.

    Admin-only endpoint. Sets the tenant-level flag that controls availability
    to members. Does not delete the underlying connection.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    try:
        from app.storage.control_plane_db import ControlPlaneSessionLocal
        from app.models.tenant import Tenant

        tenant_uuid = UUID(tenant_id)

        async with ControlPlaneSessionLocal() as cp_session:
            result = await cp_session.execute(
                select(Tenant).where(Tenant.tenant_id == tenant_uuid)
            )
            tenant_row = result.scalar_one_or_none()
            if tenant_row:
                tenant_row.google_org_workspace_enabled = request.enabled
                await cp_session.commit()

        return {
            "status": "toggled",
            "tenant_id": tenant_id,
            "enabled": request.enabled,
        }
    except Exception as e:
        logger.exception("Organization connector toggle failed")
        raise HTTPException(status_code=500, detail=f"Toggle failed: {str(e)}")


@router.post(
    "/admin/google/organization/{source_type}/backfill",
    summary="Trigger organization connector backfill",
    dependencies=[Depends(require_scope("connectors.write")), Depends(require_admin)],
)
async def trigger_organization_backfill(
    source_type: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    """
    Initiate asynchronous backfill for organization connector.

    Admin-only endpoint. Triggers backfill with explicit organization scope,
    not inferred from the calling user's personal identity.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    if source_type not in GOOGLE_SOURCES:
        raise HTTPException(status_code=400, detail=f"Invalid source_type: {source_type}")

    status_store.set_status(
        tenant_id, source_type, user_id="organization", connection_status="syncing", last_error=""
    )
    task_result = backfill_tenant_source.delay(
        tenant_id=tenant_id,
        source_type=source_type,
        user_id="organization",
    )

    return {
        "status": "queued",
        "task_id": task_result.id,
        "tenant_id": tenant_id,
        "source_type": source_type,
    }


@router.get(
    "/google/organization/status",
    summary="Get organization Google Workspace connector status",
    response_model=ConnectorStatusResponse,
    dependencies=[Depends(require_scope("connectors.read"))],
)
async def get_organization_connector_status(
    source_type: str = Query(..., description="Source type (google_drive or google_gmail)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Get organization connector status (read-only for members).

    Returns connection state, enabled state, and sync status without exposing
    admin-only actions or credentials. Resilient against unconfigured state.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")

    try:
        tenant_uuid = UUID(tenant_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid tenant ID format")

    org_enabled = False
    try:
        from app.storage.control_plane_db import ControlPlaneSessionLocal
        from app.models.tenant import Tenant
        async with ControlPlaneSessionLocal() as cp_session:
            tenant_result = await cp_session.execute(
                select(Tenant).where(Tenant.tenant_id == tenant_uuid)
            )
            tenant_row = tenant_result.scalar_one_or_none()
            org_enabled = bool(getattr(tenant_row, "google_org_workspace_enabled", False)) if tenant_row else False
    except Exception as e:
        logger.warning("Failed to check org_enabled for tenant=%s: %s", tenant_id, e)
        org_enabled = False

    row = None
    if org_enabled:
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
            async with factory() as session:
                result = await session.execute(
                    select(TenantConnector).where(
                        TenantConnector.tenant_id == tenant_uuid,
                        TenantConnector.source_type == source_type,
                        TenantConnector.connection_scope == "organization",
                    )
                )
                row = result.scalar_one_or_none()
        except Exception as e:
            logger.warning("Failed to query TenantConnector for tenant=%s source=%s: %s", tenant_id, source_type, e)
            row = None

    scope_id = f"{tenant_id}_organization"
    cursor = None
    watch_info = None
    try:
        cursor, watch_info = await cursor_store.get_cursor_and_watch(scope_id, source_type)
    except Exception:
        cursor, watch_info = None, None

    runtime = {}
    try:
        runtime = status_store.get_status(tenant_id, source_type, user_id="organization") or {}
    except Exception:
        runtime = {}

    connection_status = runtime.get("connection_status") or "not_connected"
    if row is None:
        connection_status = "not_connected"
    elif connection_status == "not_connected" and org_enabled and cursor:
        connection_status = "active" if cursor else "syncing"

    details: Dict[str, Any] = {
        "connection_status": connection_status,
        "files_indexed": runtime.get("files_indexed") or 0,
        "last_sync_at": runtime.get("last_sync_at"),
        "last_error": runtime.get("last_error"),
        "org_enabled": org_enabled,
        "connected": row is not None,
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



@router.get(
    "/{source_type}/status",
    summary="Get connector sync status",
    response_model=ConnectorStatusResponse,
    dependencies=[Depends(require_scope("connectors.read"))],
)
async def get_connector_status(
    source_type: str,
    connection_scope: str = Query("personal", description="Connection scope (personal or organization)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Retrieve sync cursor, watch flag, and runtime connection status.
    Fast read-only status query with minimal DB roundtrips.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")

    user_id = _user_id(current_user)
    scope_id = cursor_scope_id(tenant_id, user_id) if connection_scope == "personal" else f"{tenant_id}_organization"
    cursor = None
    watch_info = None
    try:
        cursor, watch_info = await cursor_store.get_cursor_and_watch(scope_id, source_type)
    except Exception:
        logger.warning(
            "cursor lookup failed tenant=%s source=%s scope=%s",
            tenant_id,
            source_type,
            scope_id,
            exc_info=True,
        )

    plugin = provider_registry.get_by_source(source_type)
    has_token = False
    try:
        if plugin and plugin.get_watch_info and source_type in ("onedrive", "outlook"):
            watch_info = await plugin.get_watch_info(scope_id, source_type)
        elif not watch_info and connection_scope != "personal":
            watch_info = await cursor_store.get_watch_info(tenant_id, source_type)
    except Exception:
        logger.warning(
            "watch lookup failed tenant=%s source=%s scope=%s",
            tenant_id,
            source_type,
            scope_id,
            exc_info=True,
        )
        watch_info = None

    runtime_user_id = user_id if connection_scope == "personal" else "organization"
    runtime_raw = status_store.get_status_raw(tenant_id, source_type, user_id=runtime_user_id)
    runtime = runtime_raw if runtime_raw is not None else status_store.get_status(
        tenant_id, source_type, user_id=runtime_user_id
    )
    if plugin and plugin.has_token and source_type in ("onedrive", "outlook"):
        has_token = bool(plugin.has_token(tenant_id, user_id))
    else:
        token_store = PersistentGoogleTokenStore(tenant_id)
        has_token = token_store.get_token(google_oauth_token_key(tenant_id, user_id, connection_scope)) is not None
        if not has_token:
            has_token = token_store.get_token(google_oauth_token_key(tenant_id, "", connection_scope)) is not None

    # Trust an explicit Redis status. Only infer when the key is missing (legacy).
    if runtime_raw is None:
        if cursor:
            connection_status = "active"
        elif has_token:
            connection_status = "syncing"
        else:
            connection_status = "not_connected"
    else:
        connection_status = runtime.get("connection_status") or "not_connected"

    details: Dict[str, Any] = {
        "connection_status": connection_status,
        "files_indexed": runtime.get("files_indexed") or 0,
        "last_sync_at": runtime.get("last_sync_at"),
        "last_error": runtime.get("last_error"),
        "token_present": has_token,
        "connection_scope": connection_scope,
    }
    if watch_info:
        details["watch_info"] = watch_info

    return ConnectorStatusResponse(
        tenant_id=tenant_id,
        source_type=source_type,
        cursor=cursor,
        watch_active=bool(watch_info),
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
    scope_id = cursor_scope_id(tenant_id, user_id)

    # Clear cursor — failure is non-fatal; log and continue.
    try:
        await cursor_store.update_cursor(scope_id, source_type, "")
    except Exception:
        logger.warning(
            "Failed to clear cursor on disconnect tenant=%s source=%s scope=%s",
            tenant_id,
            source_type,
            scope_id,
            exc_info=True,
        )

    # Always mark as not_connected in Redis regardless of DB state.
    try:
        status_store.clear_status(tenant_id, source_type, user_id=user_id)
    except Exception:
        logger.warning(
            "Failed to clear status on disconnect tenant=%s source=%s",
            tenant_id,
            source_type,
            exc_info=True,
        )

    plugin = provider_registry.get_by_source(source_type)
    if plugin and plugin.on_disconnect:
        try:
            await plugin.on_disconnect(tenant_id, user_id, source_type)
        except Exception:
            logger.exception(
                "Disconnect cleanup failed provider=%s source=%s",
                plugin.provider_id,
                source_type,
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

    State carries tenant_id + user_id + connection_scope (base64 JSON) plus a CSRF nonce.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != str(tenant_id):
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    client_id = settings.google_client_id or ""
    if not client_id:
        raise HTTPException(status_code=503, detail="GOOGLE_CLIENT_ID is not configured")

    redirect_uri = _google_redirect_uri()
    user_id = _user_id(current_user)
    state = encode_oauth_state(str(tenant_id), user_id, "personal")
    token_store = PersistentGoogleTokenStore(str(tenant_id))
    oauth = google_oauth_from_settings(token_store, principal_id=user_id, connection_scope="personal")
    auth_url = oauth.build_authorization_url(str(tenant_id), redirect_uri, state=state)

    return {
        "authorization_url": auth_url,
        "tenant_id": tenant_id,
        "connection_scope": "personal",
    }


@router.get(
    "/google/authorize/organization",
    summary="Generate Google OAuth authorization URL for organization scope",
    dependencies=[Depends(require_scope("connectors.write")), Depends(require_admin)],
)
async def get_google_authorize_url_organization(
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    """
    Generate Google OAuth authorization link for organization scope (admin-only).

    State carries tenant_id + user_id + connection_scope (base64 JSON) plus a CSRF nonce.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != str(tenant_id):
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    client_id = settings.google_client_id or ""
    if not client_id:
        raise HTTPException(status_code=503, detail="GOOGLE_CLIENT_ID is not configured")

    redirect_uri = _google_redirect_uri()
    user_id = _user_id(current_user)
    state = encode_oauth_state(str(tenant_id), user_id, "organization")
    token_store = PersistentGoogleTokenStore(str(tenant_id))
    oauth = google_oauth_from_settings(token_store, principal_id=user_id, connection_scope="organization")
    auth_url = oauth.build_authorization_url(str(tenant_id), redirect_uri, state=state)

    return {
        "authorization_url": auth_url,
        "tenant_id": tenant_id,
        "connection_scope": "organization",
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
    Handles both personal and organization connection scopes.
    """
    logger.info(f"OAuth callback invoked: error={error}, code={bool(code)}, state={bool(state)}")
    if error:
        logger.error(f"OAuth callback error: {error}")
        return RedirectResponse(frontend_connectors_redirect("error", error), status_code=302)
    if not code or not state:
        logger.error(f"OAuth callback missing code or state: code={bool(code)}, state={bool(state)}")
        return RedirectResponse(
            frontend_connectors_redirect("error", "missing_code_or_state"),
            status_code=302,
        )

    payload = decode_oauth_state(state)
    if not payload:
        logger.error(f"OAuth callback invalid state: state={state}")
        return RedirectResponse(
            frontend_connectors_redirect("error", "invalid_state"),
            status_code=302,
        )

    tenant_id = str(payload["tenant_id"])
    user_id = str(payload["user_id"])
    connection_scope = str(payload.get("connection_scope") or "personal")
    logger.info(f"OAuth callback: tenant_id={tenant_id}, user_id={user_id}, connection_scope={connection_scope}")
    redirect_uri = _google_redirect_uri()

    token_store = PersistentGoogleTokenStore(tenant_id)
    oauth = google_oauth_from_settings(token_store, principal_id=user_id, connection_scope=connection_scope)
    try:
        token_data = await oauth.exchange_code_for_tokens(tenant_id, code, redirect_uri)
    except Exception:
        return RedirectResponse(
            frontend_connectors_redirect("error", "token_exchange_failed"),
            status_code=302,
        )

    mailbox_email = await _resolve_mailbox_email(oauth, tenant_id)
    if mailbox_email or user_id:
        merged = dict(token_data or {})
        if mailbox_email:
            merged["mailbox_email"] = mailbox_email
        merged["connected_by"] = user_id
        token_store.set_token(google_oauth_token_key(tenant_id, user_id, connection_scope), merged)

    if connection_scope == "organization":
        logger.info(f"Calling _record_organization_connector_rows for tenant_id={tenant_id}, user_id={user_id}, mailbox_email={mailbox_email}")
        await _record_organization_connector_rows(tenant_id, user_id, mailbox_email)
        runtime_user_id = "organization"
    else:
        logger.info(f"Calling _record_connector_rows for tenant_id={tenant_id}, user_id={user_id}, mailbox_email={mailbox_email}")
        await _record_connector_rows(tenant_id, user_id, mailbox_email)
        runtime_user_id = user_id

    for source_type in GOOGLE_SOURCES:
        status_store.set_status(
            tenant_id,
            source_type,
            user_id=runtime_user_id,
            connection_status="syncing",
            last_error="",
        )
        try:
            backfill_source.delay(
                tenant_id=tenant_id,
                source_type=source_type,
                user_id=runtime_user_id,
                connector_id=google_credential_ref(tenant_id, user_id, connection_scope),
            )
        except Exception:
            status_store.set_status(
                tenant_id,
                source_type,
                user_id=runtime_user_id,
                connection_status="error",
                last_error="celery_enqueue_failed",
            )
            logger.exception(
                "Failed to enqueue backfill tenant=%s source=%s scope=%s", tenant_id, source_type, connection_scope
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
        logger.warning(
            "Failed to parse tenant/user UUID for connector row creation: tenant_id=%s user_id=%s",
            tenant_id,
            user_id,
        )
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
        cred_ref = google_credential_ref(tenant_id, user_id, "personal")
        async with factory() as session:
            for source_type in GOOGLE_SOURCES:
                try:
                    result = await session.execute(
                        select(TenantConnector).where(
                            TenantConnector.tenant_id == tenant_uuid,
                            TenantConnector.source_type == source_type,
                            TenantConnector.connection_scope == "personal",
                        )
                    )
                    row = result.scalar_one_or_none()
                    config = {"mailbox_email": mailbox_email, "connected_by": user_id}
                    if row is None:
                        session.add(
                            TenantConnector(
                                tenant_id=tenant_uuid,
                                source_type=source_type,
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
                    logger.info(
                        "Connector row upserted: tenant_id=%s source_type=%s enabled=True",
                        tenant_id,
                        source_type,
                    )
                except Exception as exc:
                    logger.exception(
                        "Failed to upsert connector row: tenant_id=%s source_type=%s error=%s",
                        tenant_id,
                        source_type,
                        str(exc),
                    )
                    # Continue processing other source_types - independent per source
                    # This allows Gmail to work even if Drive fails, with clear error logging
            await session.commit()
    except Exception as exc:
        logger.exception(
            "Failed to initialize connector row creation: tenant_id=%s user_id=%s error=%s",
            tenant_id,
            user_id,
            str(exc),
        )


async def _record_organization_connector_rows(tenant_id: str, user_id: str, mailbox_email: str) -> None:
    """Create organization-scoped TenantConnector rows with oauth_admin credential mode."""
    try:
        tenant_uuid = UUID(tenant_id)
        actor_uuid = UUID(user_id) if user_id else tenant_uuid
    except (TypeError, ValueError):
        logger.warning(
            "Failed to parse tenant/user UUID for org connector row creation: tenant_id=%s user_id=%s",
            tenant_id,
            user_id,
        )
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
        cred_ref = google_credential_ref(tenant_id, user_id, "organization")
        async with factory() as session:
            for source_type in GOOGLE_SOURCES:
                try:
                    result = await session.execute(
                        select(TenantConnector).where(
                            TenantConnector.tenant_id == tenant_uuid,
                            TenantConnector.source_type == source_type,
                            TenantConnector.connection_scope == "organization",
                        )
                    )
                    row = result.scalar_one_or_none()
                    config = {
                        "credential_mode": "oauth_admin",
                        "mailbox_email": mailbox_email,
                        "connected_by": user_id,
                    }
                    if row is None:
                        session.add(
                            TenantConnector(
                                tenant_id=tenant_uuid,
                                source_type=source_type,
                                connection_scope="organization",
                                enabled=True,
                                config=config,
                                setup_by=actor_uuid,
                                credential_ref=cred_ref,
                            )
                        )
                    else:
                        row.enabled = True
                        row.config = config
                        row.credential_ref = cred_ref
                        row.setup_by = actor_uuid
                    logger.info(
                        "Organization connector row upserted: tenant_id=%s source_type=%s credential_mode=oauth_admin",
                        tenant_id,
                        source_type,
                    )
                except Exception as exc:
                    logger.exception(
                        "Failed to upsert org connector row: tenant_id=%s source_type=%s error=%s",
                        tenant_id,
                        source_type,
                        str(exc),
                    )
            await session.commit()
    except Exception as exc:
        logger.exception(
            "Failed to initialize org connector row creation: tenant_id=%s user_id=%s error=%s",
            tenant_id,
            user_id,
            str(exc),
        )


@router.get(
    "/microsoft/authorize",
    summary="Generate Microsoft OAuth authorization URL",
    dependencies=[Depends(require_scope("connectors.write"))],
)
async def get_microsoft_authorize_url(
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    plugin = provider_registry.get("microsoft")
    if not plugin or not plugin.build_authorize_url:
        raise HTTPException(status_code=404, detail="Microsoft connector not configured")
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != str(tenant_id):
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")
    return await plugin.build_authorize_url(str(tenant_id), _user_id(current_user))


@router.get(
    "/microsoft/callback",
    summary="Microsoft OAuth callback — exchange code, store tokens, auto-sync",
)
async def microsoft_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    plugin = provider_registry.get("microsoft")
    if not plugin or not plugin.handle_oauth_callback:
        raise HTTPException(status_code=404, detail="Microsoft connector not configured")
    return await plugin.handle_oauth_callback(code, state, error)
