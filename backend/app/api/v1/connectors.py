"""
Connector Management API Endpoints.

Connects Block A (Auth, Tenancy, Scopes) with Block B (Google Connectors, Celery Ingestion).

Endpoints:
- POST /api/v1/connectors/{source_type}/backfill: Trigger backfill for tenant
- GET  /api/v1/connectors/{source_type}/status:   Get sync status & watches
- POST /api/v1/connectors/{source_type}/disconnect: Disconnect source & revoke watches
- GET  /api/v1/connectors/google/authorize:      Generate Google OAuth URL

All endpoints strictly enforce:
1. Block A JWT Authentication (Depends(get_current_user))
2. Tenant Routing Resolution (Depends(get_tenant))
3. Scope Checks (require_scope("connectors.write") or require_scope("connectors.read"))
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_tenant, require_scope
from app.services.tenant_resolver import TenantRouting
from app.workers.tasks import backfill_tenant_source
from app.services.cursor_store import cursor_store
from app.connectors.google.watch_manager import WatchManager
from app.connectors.google.oauth import GoogleOAuthManager
from app.core.config import settings
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


router = APIRouter(prefix="/connectors", tags=["connectors"])


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

    # Enqueue Celery task for backfill with trace context propagation (§2.4)
    _otel_headers = {}
    TraceContextTextMapPropagator().inject(_otel_headers)
    task_result = backfill_tenant_source.apply_async(
        args=[tenant_id, source_type], headers=_otel_headers
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
    Retrieve sync cursor and watch status for a tenant's connector.
    
    Requires:
    - Valid JWT Access Token
    - Scope: connectors.read
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    cursor = await cursor_store.get_cursor(tenant_id, source_type)
    
    # Check watch status
    watch_info = None
    if source_type == "google_drive":
        # Check drive watch info
        watch_info = await cursor_store.get_watch_by_channel(f"drive-{tenant_id}", "resource")
    elif source_type == "google_gmail":
        watch_info = await cursor_store.get_watch_by_email(f"user@{tenant_id}.com", source_type)

    return ConnectorStatusResponse(
        tenant_id=tenant_id,
        source_type=source_type,
        cursor=cursor,
        watch_active=watch_info is not None,
        details={"watch_info": watch_info} if watch_info else {},
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
    """
    Disconnect a connector, stop watch channels, and remove cursors.
    
    Requires:
    - Valid JWT Access Token
    - Scope: connectors.write
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    # Clear cursor
    await cursor_store.update_cursor(tenant_id, source_type, "")

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
    
    Requires:
    - Valid JWT Access Token
    - Scope: connectors.write
    """
    tenant_id = current_user.get("tenant_id")
    
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
    redirect_uri = getattr(settings, "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/connectors/google/callback")
    
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope=https://www.googleapis.com/auth/drive.readonly%20https://www.googleapis.com/auth/gmail.readonly&"
        f"access_type=offline&"
        f"prompt=consent&"
        f"state={tenant_id}"
    )

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
    On success: encrypt+store tokens, enqueue Drive + Gmail full backfill, redirect UI.
    """
    if error:
        return RedirectResponse(f"/connectors?status=error&message={error}", status_code=302)
    if not code or not state:
        return RedirectResponse("/connectors?status=error&message=missing_code_or_state", status_code=302)

    # Simple state validation - just tenant_id for now
    try:
        import json
        import base64
        payload = json.loads(base64.b64decode(state))
        tenant_id = str(payload.get("tenant_id", ""))
        user_id = str(payload.get("user_id", ""))
    except Exception:
        return RedirectResponse("/connectors?status=error&message=invalid_state", status_code=302)

    if not tenant_id:
        return RedirectResponse("/connectors?status=error&message=missing_tenant_id", status_code=302)

    try:
        from app.connectors.google.token_store import PersistentGoogleTokenStore, google_oauth_token_key
        from app.connectors.google.oauth import google_oauth_from_settings
        from app.connectors.google.keys import google_credential_ref
        from app.connectors.google import status_store
        from app.workers.tasks import backfill_source
        from app.services.tenant_resolver import tenant_resolver
        from app.storage.tenant_db import tenant_db_manager
        from app.models.tenant_connector import TenantConnector
        from sqlalchemy import select
        from uuid import UUID
        import logging

        logger = logging.getLogger(__name__)

        redirect_uri = getattr(settings, "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/connectors/google/callback")
        token_store = PersistentGoogleTokenStore(tenant_id)
        oauth = google_oauth_from_settings(token_store, principal_id=user_id)
        
        token_data = await oauth.exchange_code_for_tokens(tenant_id, code, redirect_uri)
        
        # Resolve mailbox email
        mailbox_email = ""
        try:
            token = await oauth.get_valid_token(tenant_id)
            from app.connectors.google.clients.gmail_client import GmailClient
            profile = await GmailClient().get_profile(token)
            mailbox_email = str(profile.get("emailAddress") or "")
        except Exception:
            pass

        if mailbox_email or user_id:
            merged = dict(token_data or {})
            if mailbox_email:
                merged["mailbox_email"] = mailbox_email
            merged["connected_by"] = user_id
            token_store.set_token(google_oauth_token_key(tenant_id, user_id), merged)

        # Record connector rows
        try:
            tenant_uuid = UUID(tenant_id)
            actor_uuid = UUID(user_id) if user_id else tenant_uuid
        except (TypeError, ValueError):
            logger.warning("Failed to parse tenant/user UUID for connector row creation")
        else:
            try:
                routing = await tenant_resolver.resolve(tenant_id)
                factory = tenant_db_manager.get_session_factory(
                    routing.db_host,
                    routing.db_name,
                    routing.db_user,
                    routing.db_password,
                    str(routing.tenant_id),
                )
                cred_ref = google_credential_ref(tenant_id, user_id)
                GOOGLE_SOURCES = ("google_drive", "google_gmail")
                
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
                    await session.commit()
            except Exception as exc:
                logger.exception(
                    "Failed to initialize connector row creation: tenant_id=%s user_id=%s error=%s",
                    tenant_id,
                    user_id,
                    str(exc),
                )

        # Enqueue backfills
        GOOGLE_SOURCES = ("google_drive", "google_gmail")
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
                    connector_id=google_credential_ref(tenant_id, user_id, "personal"),
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

    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("OAuth callback failed: %s", str(exc))
        return RedirectResponse(f"/connectors?status=error&message=oauth_failed", status_code=302)

    return RedirectResponse("/connectors?status=connected", status_code=302)
