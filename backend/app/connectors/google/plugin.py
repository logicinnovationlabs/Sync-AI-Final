"""Google Workspace provider plugin — OAuth + status/disconnect/backfill hooks."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.connectors.google import status_store
from app.connectors.google.keys import google_oauth_token_key
from app.connectors.google.oauth import google_oauth_from_settings, seed_token_store_from_env
from app.connectors.google.oauth_state import (
    decode_oauth_state,
    encode_oauth_state,
    frontend_connectors_redirect,
)
from app.connectors.google.token_store import (
    PersistentGoogleTokenStore,
    google_credential_ref,
)
from app.connectors.google.watch_manager import WatchManager
from app.connectors.google.webhooks import router as google_webhooks_router
from app.connectors.plugin_base import BackfillAuth, ProviderPlugin
from app.core.config import settings
from app.services.cursor_store import cursor_store

logger = logging.getLogger(__name__)

SOURCES = ("google_drive", "google_gmail")
_DEFAULT_CALLBACK = "http://localhost:8000/connectors/google/callback"


def _redirect_uri() -> str:
    return (settings.google_redirect_uri or _DEFAULT_CALLBACK).rstrip("/")


def has_token(tenant_id: str, user_id: str) -> bool:
    token_store = PersistentGoogleTokenStore(tenant_id)
    if token_store.get_token(google_oauth_token_key(tenant_id, user_id)) is not None:
        return True
    return token_store.get_token(google_oauth_token_key(tenant_id)) is not None


async def get_watch_info(scope_id: str, source_type: str) -> Any:
    if source_type == "google_drive":
        return await cursor_store.get_watch_by_channel(f"drive-{scope_id}", "resource")
    if source_type == "google_gmail":
        return await cursor_store.get_watch_by_email(
            f"user@{scope_id}.com", source_type
        )
    return None


async def _delete_personal_connector_row(tenant_id: str, source_type: str) -> None:
    try:
        tenant_uuid = UUID(tenant_id)
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
        async with factory() as session:
            result = await session.execute(
                select(TenantConnector).where(
                    TenantConnector.tenant_id == tenant_uuid,
                    TenantConnector.source_type == source_type,
                    TenantConnector.connection_scope == "personal",
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                await session.delete(row)
                await session.commit()
    except Exception:
        logger.warning(
            "Failed to delete TenantConnector row tenant=%s source=%s",
            tenant_id,
            source_type,
            exc_info=True,
        )


async def on_disconnect(tenant_id: str, user_id: str, source_type: str) -> None:
    """Clear watches, tokens (when sibling Google source is gone), and DB rows."""
    scope_id = cursor_scope_id(tenant_id, user_id)
    try:
        await cursor_store.clear_watch_info(scope_id, source_type)
    except Exception:
        logger.warning(
            "Failed to clear watch_data tenant=%s source=%s",
            tenant_id,
            source_type,
            exc_info=True,
        )

    await _delete_personal_connector_row(tenant_id, source_type)

    other = "google_gmail" if source_type == "google_drive" else "google_drive"
    other_status = status_store.get_status(tenant_id, other, user_id=user_id)
    if other_status.get("connection_status") in (None, "", "not_connected"):
        token_store = PersistentGoogleTokenStore(tenant_id)
        token_store.clear_token(google_oauth_token_key(tenant_id, user_id, "personal"))
        token_store.clear_token(google_oauth_token_key(tenant_id, "", "personal"))
        token_store.clear_token(google_oauth_token_key(tenant_id, user_id))
        token_store.clear_token(google_oauth_token_key(tenant_id))


async def build_authorize_url(tenant_id: str, user_id: str) -> Dict[str, Any]:
    client_id = settings.google_client_id or ""
    if not client_id:
        raise HTTPException(status_code=503, detail="GOOGLE_CLIENT_ID is not configured")
    redirect_uri = _redirect_uri()
    state = encode_oauth_state(str(tenant_id), user_id)
    token_store = PersistentGoogleTokenStore(str(tenant_id))
    oauth = google_oauth_from_settings(token_store, principal_id=user_id)
    auth_url = oauth.build_authorization_url(str(tenant_id), redirect_uri, state=state)
    return {"authorization_url": auth_url, "tenant_id": tenant_id}


async def _resolve_mailbox_email(oauth, tenant_id: str) -> str:
    try:
        token = await oauth.get_valid_token(tenant_id)
        from app.connectors.google.clients.gmail_client import GmailClient

        profile = await GmailClient().get_profile(token)
        return str(profile.get("emailAddress") or "")
    except Exception:
        return ""


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
        cred_ref = google_credential_ref(tenant_id, user_id)
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

    if error:
        return RedirectResponse(
            frontend_connectors_redirect("error", error), status_code=302
        )
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
    redirect_uri = _redirect_uri()
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
    if mailbox_email or user_id:
        merged = dict(token_data or {})
        if mailbox_email:
            merged["mailbox_email"] = mailbox_email
        merged["connected_by"] = user_id
        token_store.set_token(google_oauth_token_key(tenant_id, user_id), merged)
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
                "Failed to enqueue backfill tenant=%s source=%s",
                tenant_id,
                source_type,
            )

    return RedirectResponse(frontend_connectors_redirect("connected"), status_code=302)


def prepare_backfill(
    tenant_id: str, source_type: str, principal_id: str
) -> BackfillAuth:
    from app.connectors.google.oauth import GoogleOAuthManager

    token_store = PersistentGoogleTokenStore(tenant_id)
    oauth_manager = GoogleOAuthManager(
        token_store,
        settings.google_client_id or "",
        settings.google_client_secret or "",
        [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/userinfo.email",
            "openid",
        ],
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
        data = token_store.get_token(google_oauth_token_key(tenant_id, principal_id)) or {}
        if not data.get("mailbox_email"):
            data = token_store.get_token(google_oauth_token_key(tenant_id)) or {}
        mailbox = str(data.get("mailbox_email") or "")
        if not principal_id:
            principal_id = str(
                data.get("connected_by") or data.get("user_id") or ""
            ).strip()
    except Exception:
        pass

    return BackfillAuth(
        token_store=token_store,
        oauth_manager=oauth_manager,
        principal_id=principal_id,
        mailbox_email=mailbox,
        client_id=settings.google_client_id or "",
        client_secret=settings.google_client_secret or "",
        allow_env_seed=True,
    )


def maybe_seed_env(auth: BackfillAuth, tenant_id: str) -> None:
    if not auth.allow_env_seed or auth.principal_id:
        return
    seed_token_store_from_env(
        auth.token_store,
        tenant_id,
        client_id=auth.client_id,
        client_secret=auth.client_secret,
        refresh_token=getattr(settings, "google_refresh_token", None),
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

    if source_type == "google_drive":
        watch_manager = WatchManager(oauth_manager, cursor_store, webhook_base_url)
        _run_async(watch_manager.register_drive_watch(tenant_id, final_cursor))
    elif source_type == "google_gmail":
        watch_manager = WatchManager(oauth_manager, cursor_store, webhook_base_url)
        pubsub_topic = getattr(settings, "google_pubsub_topic", None) or ""
        project_id = getattr(settings, "google_pubsub_project_id", None) or ""
        if pubsub_topic and project_id:
            full_topic = f"projects/{project_id}/topics/{pubsub_topic}"
            _run_async(
                watch_manager.register_gmail_watch(tenant_id, final_cursor, full_topic)
            )


plugin = ProviderPlugin(
    provider_id="google",
    sources=SOURCES,
    celery_queue="google",
    webhook_router=google_webhooks_router,
    build_authorize_url=build_authorize_url,
    handle_oauth_callback=handle_oauth_callback,
    has_token=has_token,
    get_watch_info=get_watch_info,
    on_disconnect=on_disconnect,
    prepare_backfill=prepare_backfill,
    register_watch=register_watch,
    celery_task_routes={
        "app.workers.tasks.backfill_tenant_source": "google",
        "app.workers.tasks.backfill_source": "google",
        "app.workers.tasks.process_drive_notification": "google",
        "app.workers.tasks.process_gmail_notification": "google",
        "app.workers.tasks.renew_watch_channels": "google",
        "app.workers.tasks.google_queue_ping": "google",
    },
)
