"""Microsoft 365 provider plugin — OAuth + status/disconnect/backfill hooks."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.connectors.google import status_store
from app.connectors.google.keys import cursor_scope_id
from app.connectors.google.oauth_state import (
    decode_oauth_state,
    encode_oauth_state,
    frontend_connectors_redirect,
)
from app.connectors.microsoft.keys import microsoft_oauth_token_key
from app.connectors.microsoft.oauth import (
    MicrosoftOAuthManager,
    microsoft_oauth_from_settings,
)
from app.connectors.microsoft.token_store import (
    PersistentMicrosoftTokenStore,
    microsoft_credential_ref,
)
from app.connectors.microsoft.watch_manager import MicrosoftWatchManager
from app.connectors.microsoft.webhooks import router as microsoft_webhooks_router
from app.connectors.plugin_base import BackfillAuth, ProviderPlugin
from app.core.config import settings
from app.services.cursor_store import cursor_store

logger = logging.getLogger(__name__)

SOURCES = ("onedrive", "outlook")
_DEFAULT_CALLBACK = "http://localhost:8000/connectors/microsoft/callback"
_MS_SCOPES = [
    "offline_access",
    "openid",
    "profile",
    "email",
    "User.Read",
    "Files.Read",
    "Files.Read.All",
    "Mail.Read",
]


def _redirect_uri() -> str:
    return (settings.microsoft_redirect_uri or _DEFAULT_CALLBACK).rstrip("/")


def has_token(tenant_id: str, user_id: str) -> bool:
    ms_store = PersistentMicrosoftTokenStore(tenant_id)
    if ms_store.get_token(microsoft_oauth_token_key(tenant_id, user_id)) is not None:
        return True
    return ms_store.get_token(microsoft_oauth_token_key(tenant_id)) is not None


async def get_watch_info(scope_id: str, source_type: str) -> Any:
    watch_info_raw = await cursor_store.get_watch_info(scope_id, source_type)
    if not watch_info_raw:
        return None
    return {
        "tenant_id": scope_id,
        "source_type": source_type,
        "watch_data": watch_info_raw,
    }


async def on_disconnect(tenant_id: str, user_id: str, source_type: str) -> None:
    ms_store = PersistentMicrosoftTokenStore(tenant_id)
    oauth = microsoft_oauth_from_settings(ms_store, principal_id=user_id)
    webhook_base = getattr(settings, "webhook_base_url", None) or "http://localhost:8000"
    watch_mgr = MicrosoftWatchManager(oauth, cursor_store, webhook_base)
    await watch_mgr.delete_subscription(tenant_id, source_type, user_id=user_id)
    try:
        await cursor_store.clear_watch_info(
            cursor_scope_id(tenant_id, user_id), source_type
        )
    except Exception:
        logger.warning(
            "Failed to clear MS watch_data tenant=%s source=%s",
            tenant_id,
            source_type,
            exc_info=True,
        )
    other = "outlook" if source_type == "onedrive" else "onedrive"
    other_status = status_store.get_status(tenant_id, other, user_id=user_id)
    if other_status.get("connection_status") in (None, "", "not_connected"):
        ms_store.clear_token(microsoft_oauth_token_key(tenant_id, user_id))
        ms_store.clear_token(microsoft_oauth_token_key(tenant_id))


async def build_authorize_url(tenant_id: str, user_id: str) -> Dict[str, Any]:
    client_id = settings.microsoft_client_id or ""
    if not client_id:
        raise HTTPException(
            status_code=503, detail="MICROSOFT_CLIENT_ID is not configured"
        )
    redirect_uri = _redirect_uri()
    state = encode_oauth_state(str(tenant_id), user_id)
    token_store = PersistentMicrosoftTokenStore(str(tenant_id))
    oauth = microsoft_oauth_from_settings(token_store, principal_id=user_id)
    auth_url = oauth.build_authorization_url(str(tenant_id), redirect_uri, state=state)
    return {"authorization_url": auth_url, "tenant_id": tenant_id}


async def _record_connector_rows(
    tenant_id: str, user_id: str, mailbox_email: str
) -> None:
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
        cred_ref = microsoft_credential_ref(tenant_id, user_id)
        async with factory() as session:
            for source_type in SOURCES:
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


async def handle_oauth_callback(
    code: Optional[str],
    state: Optional[str],
    error: Optional[str],
) -> RedirectResponse:
    from app.workers.tasks import backfill_source
    from app.connectors.microsoft.clients.graph_client import GraphClient

    if error:
        return RedirectResponse(
            frontend_connectors_redirect("error", error, provider="microsoft"),
            status_code=302,
        )
    if not code or not state:
        return RedirectResponse(
            frontend_connectors_redirect(
                "error", "missing_code_or_state", provider="microsoft"
            ),
            status_code=302,
        )

    payload = decode_oauth_state(state)
    if not payload:
        return RedirectResponse(
            frontend_connectors_redirect(
                "error", "invalid_state", provider="microsoft"
            ),
            status_code=302,
        )

    tenant_id = str(payload["tenant_id"])
    user_id = str(payload["user_id"])
    redirect_uri = _redirect_uri()
    token_store = PersistentMicrosoftTokenStore(tenant_id)
    oauth = microsoft_oauth_from_settings(token_store, principal_id=user_id)
    try:
        token_data = await oauth.exchange_code_for_tokens(tenant_id, code, redirect_uri)
    except Exception:
        logger.exception(
            "Microsoft token exchange failed tenant=%s redirect_uri=%s",
            tenant_id,
            redirect_uri,
        )
        return RedirectResponse(
            frontend_connectors_redirect(
                "error", "token_exchange_failed", provider="microsoft"
            ),
            status_code=302,
        )

    mailbox_email = ""
    try:
        access = await oauth.get_valid_token(tenant_id)
        me = await GraphClient().get_me(access)
        mailbox_email = str(me.get("mail") or me.get("userPrincipalName") or "")
    except Exception:
        mailbox_email = ""

    merged = dict(token_data or {})
    if mailbox_email:
        merged["mailbox_email"] = mailbox_email
    merged["connected_by"] = user_id
    token_store.set_token(microsoft_oauth_token_key(tenant_id, user_id), merged)
    await _record_connector_rows(tenant_id, user_id, mailbox_email)

    for source_type in SOURCES:
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
                connector_id=microsoft_credential_ref(tenant_id, user_id),
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
                "Failed to enqueue Microsoft backfill tenant=%s source=%s",
                tenant_id,
                source_type,
            )

    return RedirectResponse(
        frontend_connectors_redirect("connected", provider="microsoft"),
        status_code=302,
    )


def prepare_backfill(
    tenant_id: str, source_type: str, principal_id: str
) -> BackfillAuth:
    token_store = PersistentMicrosoftTokenStore(tenant_id)
    oauth_manager = MicrosoftOAuthManager(
        token_store,
        settings.microsoft_client_id or "",
        settings.microsoft_client_secret or "",
        list(_MS_SCOPES),
        tenant=getattr(settings, "microsoft_tenant", None) or "common",
        principal_id=principal_id,
    )
    status_store.set_status(
        tenant_id,
        source_type,
        user_id=principal_id,
        connection_status="syncing",
        last_error="",
    )
    mailbox = ""
    try:
        blob = (
            token_store.get_token(microsoft_oauth_token_key(tenant_id, principal_id))
            or token_store.get_token(microsoft_oauth_token_key(tenant_id))
            or {}
        )
        mailbox = str(blob.get("mailbox_email") or "")
        if not principal_id:
            principal_id = str(blob.get("connected_by") or "").strip()
    except Exception:
        pass

    return BackfillAuth(
        token_store=token_store,
        oauth_manager=oauth_manager,
        principal_id=principal_id,
        mailbox_email=mailbox,
    )


def register_watch(
    oauth_manager,
    tenant_id: str,
    source_type: str,
    final_cursor: Optional[str],
    user_id: str,
    webhook_base_url: str,
) -> None:
    if not final_cursor or oauth_manager is None:
        return
    from app.workers.tasks import _run_async

    ms_watch = MicrosoftWatchManager(oauth_manager, cursor_store, webhook_base_url)
    if source_type == "onedrive":
        _run_async(ms_watch.register_onedrive_subscription(tenant_id, user_id=user_id))
    else:
        _run_async(ms_watch.register_outlook_subscription(tenant_id, user_id=user_id))


def process_notification(source_type: str, tenant_id: str, user_id: str = "") -> dict:
    """Incremental Graph sync for OneDrive/Outlook (Celery)."""
    from app.workers.tasks import _run_async, _validate_tenant_auth, indexer
    from app.connectors.microsoft.services.onedrive_service import OneDriveConnector
    from app.connectors.microsoft.services.outlook_service import OutlookConnector

    _validate_tenant_auth(tenant_id)
    principal_id = str(user_id or "").strip()
    scope_id = cursor_scope_id(tenant_id, principal_id)
    cursor = _run_async(cursor_store.get_cursor(scope_id, source_type))
    if not cursor:
        return {"status": "no_cursor", "indexed_count": 0, "deleted_count": 0}

    token_store = PersistentMicrosoftTokenStore(tenant_id)
    oauth = MicrosoftOAuthManager(
        token_store,
        settings.microsoft_client_id or "",
        settings.microsoft_client_secret or "",
        list(_MS_SCOPES),
        tenant=getattr(settings, "microsoft_tenant", None) or "common",
        principal_id=principal_id,
    )
    mailbox = ""
    try:
        blob = (
            token_store.get_token(microsoft_oauth_token_key(tenant_id, principal_id))
            or token_store.get_token(microsoft_oauth_token_key(tenant_id))
            or {}
        )
        mailbox = str(blob.get("mailbox_email") or "")
    except Exception:
        pass

    config = {
        "tenant_id": tenant_id,
        "mailbox_email": mailbox,
        "connected_by": principal_id,
    }
    if source_type == "onedrive":
        connector = OneDriveConnector(config, token_store, oauth)
    else:
        connector = OutlookConnector(config, token_store, oauth)

    delta_result = _run_async(connector.fetch_since_delta_link(cursor))
    deleted_ids = []
    if getattr(delta_result, "documents", None):
        unified = _run_async(connector.transform(delta_result.documents))
        if unified:
            _run_async(indexer.bulk_index(unified, tenant_id))
    if source_type == "onedrive":
        for raw in getattr(delta_result, "documents", []) or []:
            if raw.get("@removed") and raw.get("id"):
                deleted_ids.append(f"onedrive:{raw['id']}")
    if deleted_ids:
        _run_async(indexer.delete_by_ids(deleted_ids, tenant_id, source_type))
    if getattr(delta_result, "next_cursor", None):
        _run_async(
            cursor_store.update_cursor(scope_id, source_type, delta_result.next_cursor)
        )
    return {
        "status": "success",
        "indexed_count": len(getattr(delta_result, "documents", []) or []),
        "deleted_count": len(deleted_ids),
    }


async def microsoft_oauth_callback_endpoint(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """Legacy Azure redirect target: GET /outlook/callback."""
    return await handle_oauth_callback(code, state, error)


plugin = ProviderPlugin(
    provider_id="microsoft",
    sources=SOURCES,
    celery_queue="microsoft",
    webhook_router=microsoft_webhooks_router,
    legacy_routes=(
        ("/outlook/callback", microsoft_oauth_callback_endpoint, ("GET",)),
    ),
    build_authorize_url=build_authorize_url,
    handle_oauth_callback=handle_oauth_callback,
    has_token=has_token,
    get_watch_info=get_watch_info,
    on_disconnect=on_disconnect,
    prepare_backfill=prepare_backfill,
    register_watch=register_watch,
    process_notification=process_notification,
    celery_task_routes={
        "app.workers.tasks.process_connector_notification": "microsoft",
        "app.workers.tasks.process_onedrive_notification": "microsoft",
        "app.workers.tasks.process_outlook_notification": "microsoft",
    },
)
