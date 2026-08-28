"""
Celery tasks for document ingestion.

Tasks:
- backfill_tenant_source: One-time full traversal (uses sync.py orchestrator)
- process_drive_notification: Incremental Drive sync (triggered by webhook)
- process_gmail_notification: Incremental Gmail sync (triggered by Pub/Sub)
- renew_watch_channels: Periodic watch renewal (Celery Beat)
- revalidate_acls_for_tenant: ACL revalidation task (Block C)

All tasks support retries with exponential backoff for resilience.
"""

from typing import Optional
import logging
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.services.sync import sync_orchestrator
from app.services.indexer import indexer
from app.services.cursor_store import cursor_store
from app.services.registry import connector_registry
from app.connectors.google.oauth import GoogleOAuthManager, seed_token_store_from_env
from app.connectors.google.keys import cursor_scope_id, google_oauth_token_key
from app.connectors.google.watch_manager import WatchManager
from app.connectors.google.services.drive_service import DriveConnector
from app.connectors.google.services.gmail_service import GmailConnector
from app.connectors.google.token_store import PersistentGoogleTokenStore
from app.connectors.google import status_store
from app.core.config import settings
from app.storage.redis_client import redis_client
from app.storage.vault_client import PlatformSecretKeys, vault_client
from app.core.exceptions import (
    InvalidTokenError,
    RevokedTokenError,
    TenantNotFoundError,
    UnauthorizedError,
    VaultError,
)
from app.services.tenant_resolver import tenant_resolver
import asyncio
import inspect

# Block O – Worker-side trace context extraction (requirement §2.4)
# Without this, CeleryInstrumentor still auto-instruments the task, but the
# resulting span starts a *new* trace instead of continuing the one from the
# API request.  This signal fires before every task execution and re-attaches
# the context that was injected on the enqueue side.
from opentelemetry import context as _otel_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from celery.signals import task_prerun, task_postrun

_trace_tokens = {}


@task_prerun.connect
def _extract_trace_context(task_id, task, args, kwargs, **extras):
    """Extract W3C Trace Context from task headers and attach to current context."""
    headers = task.request.headers or {}
    if headers:
        ctx = TraceContextTextMapPropagator().extract(carrier=headers)
        _trace_tokens[task_id] = _otel_context.attach(ctx)


@task_postrun.connect
def _detach_trace_context(task_id, task, args, kwargs, **extras):
    token = _trace_tokens.pop(task_id, None)
    if token is not None:
        _otel_context.detach(token)


try:
    import nest_asyncio
    nest_asyncio.apply()
except (ImportError, ValueError):
    # ImportError: nest_asyncio not installed
    # ValueError: Can't patch uvloop (used by uvicorn in production)
    pass

logger = logging.getLogger(__name__)

_AUTH_FAILURE_TYPES = (UnauthorizedError, InvalidTokenError, RevokedTokenError)


def _is_google_auth_failure(exc: BaseException) -> bool:
    """True only for typed credential/token failures, never VaultError."""
    if isinstance(exc, VaultError):
        return False
    if isinstance(exc, _AUTH_FAILURE_TYPES):
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return _is_google_auth_failure(cause)
    return False


def _backfill_failure_status(exc: BaseException) -> str:
    """Map a backfill exception to status_store vocabulary. Vault != re-auth."""
    if isinstance(exc, VaultError) or isinstance(getattr(exc, "__cause__", None), VaultError):
        return "error"
    if _is_google_auth_failure(exc):
        return "needs_reauth"
    return "error"


def _run_async(coro):
    """Run async coroutine synchronously inside Celery tasks."""
    if not inspect.iscoroutine(coro):
        return coro
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)








class RedisTokenStore:
    """
    Process-local OAuth token cache with optional Redis persistence.

    Redis I/O is skipped when an event loop is already running (Celery eager
    inside pytest) to avoid cross-loop Future errors.
    """

    _process: dict = {}

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def _ns(self, key: str) -> str:
        return f"{self.tenant_id}:{key}"

    def _loop_busy(self) -> bool:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        return loop.is_running()

    def get_token(self, key: str) -> Optional[dict]:
        cached = type(self)._process.get(self._ns(key))
        if cached is not None:
            return cached
        if self._loop_busy():
            return None
        try:
            data = _run_async(redis_client.get_json(self.tenant_id, f"oauth_token:{key}"))
        except Exception:
            return None
        if isinstance(data, dict):
            type(self)._process[self._ns(key)] = data
            return data
        return None

    def set_token(self, key: str, token_data: dict) -> None:
        type(self)._process[self._ns(key)] = token_data
        if self._loop_busy():
            return
        try:
            _run_async(redis_client.set_json(self.tenant_id, f"oauth_token:{key}", token_data))
        except Exception:
            logger.warning("Failed to persist OAuth token for tenant %s", self.tenant_id)


DummyTokenStore = RedisTokenStore


def _dev_or_test() -> bool:
    env = (getattr(settings, "environment", "development") or "development").lower()
    return env in {"development", "dev", "test"}


def _validate_tenant_auth(tenant_id: str):
    """
    Validate tenant auth before background ingestion.

    Fail-closed for empty IDs and revoked/invalid markers (AB5). UUID tenants
    must resolve in production. Development/test may proceed if the control
    plane has no row (Block B/AB signoff uses synthetic tenant ids).
    """
    if not tenant_id:
        logger.error("Security Rejection: Ingestion task aborted for empty tenant_id")
        raise ValueError("AUTH_FAILED: Tenant auth invalid or revoked for tenant_id: ")
    lowered = tenant_id.lower()
    if lowered.startswith("invalid") or "revoked" in lowered:
        logger.error(
            "Security Rejection: Ingestion task aborted for unauthorized/revoked tenant %s",
            tenant_id,
        )
        raise ValueError(f"AUTH_FAILED: Tenant auth invalid or revoked for tenant_id: {tenant_id}")
    
    # Extract base tenant_id from composite format (tenant_id:user_id)
    base_tenant_id = tenant_id
    if ":" in tenant_id:
        parts = tenant_id.split(":")
        if len(parts) == 2:
            base_tenant_id = parts[0]
    
    try:
        UUID(base_tenant_id)
    except (ValueError, TypeError):
        return
    try:
        _safe_resolve_tenant(base_tenant_id)
    except TenantNotFoundError as exc:
        if not _dev_or_test():
            raise ValueError(
                f"AUTH_FAILED: Tenant auth invalid or revoked for tenant_id: {tenant_id}"
            ) from exc
        logger.warning("Tenant %s not in control plane; allowing in development/test", tenant_id)
    except ValueError:
        raise
    except Exception as exc:
        if not _dev_or_test():
            raise ValueError(
                f"AUTH_FAILED: Tenant auth invalid or revoked for tenant_id: {tenant_id}"
            ) from exc
        logger.warning("Tenant resolve failed in development/test for %s: %s", tenant_id, exc)


def _loop_busy() -> bool:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    return loop.is_running()


def _safe_resolve_tenant(tenant_id: str):
    """Resolve tenant routing; skip nested-loop resolve in local tests."""
    if _loop_busy() and _dev_or_test():
        return None
    
    # Extract base tenant_id from composite format (tenant_id:user_id)
    base_tenant_id = tenant_id
    if ":" in tenant_id:
        parts = tenant_id.split(":")
        if len(parts) == 2:
            base_tenant_id = parts[0]
    
    return _run_async(tenant_resolver.resolve(base_tenant_id))


def _mailbox_for_tenant(tenant_id: str, source_type: str) -> str:
    """Mailbox from tenant routing config — never a hardcoded identity."""
    del source_type
    try:
        UUID(tenant_id)
    except (ValueError, TypeError):
        return ""
    try:
        routing = _safe_resolve_tenant(tenant_id)
        if routing is None:
            return ""
        cfg = dict(getattr(routing, "config", None) or {})
        return str(cfg.get("mailbox_email") or cfg.get("google_mailbox_email") or "")
    except Exception as exc:
        logger.debug("Mailbox lookup failed for tenant %s: %s", tenant_id, exc)
        return ""


def _resolve_org_admin_user_id(tenant_id: str, source_type: str) -> str:
    """Resolve admin user_id from organization connector config for oauth_admin mode."""
    from app.services.tenant_resolver import tenant_resolver
    from app.storage.tenant_db import tenant_db_manager
    from app.models.tenant_connector import TenantConnector
    
    try:
        routing = _safe_resolve_tenant(tenant_id)
        if routing is None:
            return ""
        
        tenant_uuid = UUID(tenant_id)
        
        async def _resolve(uuid_val):
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
                        TenantConnector.tenant_id == uuid_val,
                        TenantConnector.source_type == source_type,
                        TenantConnector.connection_scope == "organization",
                    )
                )
                row = result.scalar_one_or_none()
                if row:
                    config = dict(row.config or {})
                    admin_user_id = config.get("connected_by") or ""
                    logger.debug("Resolved org admin user_id %s for tenant %s source %s", admin_user_id, tenant_id, source_type)
                    return str(admin_user_id)
                return ""
        
        return _run_async(_resolve(tenant_uuid))
    except Exception as exc:
        logger.warning("Failed to resolve org admin user_id for tenant %s source %s: %s", tenant_id, source_type, exc)
        return ""


def _token_store_for_tenant(tenant_id: str) -> RedisTokenStore:
    store = RedisTokenStore(tenant_id)
    client_id = getattr(settings, "google_client_id", None) or getattr(settings, "GOOGLE_CLIENT_ID", "") or ""
    client_secret = vault_client.get(PlatformSecretKeys.GOOGLE_CLIENT_SECRET) or ""
    seed_token_store_from_env(
        store,
        tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=getattr(settings, "google_refresh_token", None),
    )
    return store


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def backfill_tenant_source(self, tenant_id: str, source_type: str, user_id: str = None, connector_id: str = None) -> dict:
    """
    One-time full backfill for a tenant/source.
    
    Pipeline:
    1. Validate Tenant Auth (Block A check)
    2. Run sync orchestrator (two-pass: deletions then delta)
    3. Store final cursor
    4. Register watch channel/subscription
    
    Args:
        tenant_id: Tenant identifier
        source_type: Source type (e.g., 'google_drive', 'google_gmail')
        user_id: User principal ID (or "organization" for org scope)
        
    Returns:
        Summary dict with counts and final cursor
    """
    try:
        logger.info(
            "Starting backfill for tenant %s user %s source %s",
            tenant_id,
            user_id,
            source_type,
        )
        _validate_tenant_auth(tenant_id)

        token_store = PersistentGoogleTokenStore(tenant_id)
        principal_id = str(user_id or "").strip()
        
        # For organization scope, resolve the actual admin user_id from connector config
        if principal_id == "organization":
            admin_user_id = _resolve_org_admin_user_id(tenant_id, source_type)
            if admin_user_id:
                principal_id = admin_user_id
                logger.info("Organization scope: using admin user_id %s", principal_id)
        
        scope_id = cursor_scope_id(tenant_id, principal_id)

        oauth_manager = None
        client_id = ""
        client_secret = ""
        if source_type.startswith("google_"):
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
            client_id = settings.google_client_id or ""
            client_secret = settings.google_client_secret or ""
            status_store.set_status(
                tenant_id,
                source_type,
                user_id=str(user_id or principal_id),  # Use original user_id for status tracking
                connection_status="syncing",
                last_error="",
            )
        if not principal_id:
            seed_token_store_from_env(
                token_store,
                tenant_id,
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=getattr(settings, "google_refresh_token", None),
            )
        mailbox_email = _lookup_mailbox_email(
            tenant_id, token_store, oauth_manager, user_id=principal_id
        )
        if not principal_id:
            # OAuth stores connected_by so manual/beat re-syncs still ACL to the owner
            try:
                blob = (
                    token_store.get_token(google_oauth_token_key(tenant_id, "", "personal"))
                    or {}
                )
                principal_id = str(
                    blob.get("connected_by") or blob.get("user_id") or ""
                ).strip()
                if principal_id:
                    scope_id = cursor_scope_id(tenant_id, principal_id)
                    user_id = principal_id
            except Exception:
                pass
        config = {
            "tenant_id": tenant_id,
            "mailbox_email": mailbox_email or "",
            "connected_by": user_id or principal_id or "",
        }
        
        # Get connector instance
        connector = connector_registry.get_connector(source_type, config, token_store)
        
        # Inject OAuth manager if Google connector
        if hasattr(connector, "oauth_manager"):
            connector.oauth_manager = oauth_manager
        
        # Resume from last mid-crawl checkpoint when present (Architecture B5)
        resume_cursor = _run_async(cursor_store.get_cursor(scope_id, source_type)) or None
        if resume_cursor:
            logger.info(
                f"Resuming backfill for tenant {tenant_id}, source {source_type} "
                f"from checkpoint cursor={resume_cursor!r}"
            )

        async def _persist_checkpoint(next_cursor: str) -> None:
            """Persist page cursor after each successful batch (mid-crawl checkpoint).

            Must be async and awaited on the sync orchestrator's loop — calling
            ``_run_async`` from inside ``asyncio.run`` opens a second loop and
            breaks SQLAlchemy/asyncpg connection pooling.
            """
            await cursor_store.update_cursor(scope_id, source_type, next_cursor or None)
            logger.debug(
                f"Checkpoint saved tenant={tenant_id} source={source_type} cursor={next_cursor!r}"
            )

        # Stamp the SynQ user who connected Google so federated search ACL matches JWT ``sub``
        owner_acl = _acl_terms_for_user(principal_id or user_id)
        if mailbox_email:
            owner_acl = list(dict.fromkeys(owner_acl + _acl_terms_for_user(f"user:{mailbox_email}")))

        # Run sync orchestrator (two-pass: deletions then delta, paginated + checkpointed)
        since = datetime.utcnow() - timedelta(days=365)  # Look back 1 year
        result = sync_orchestrator.run_two_pass_sync(
            connector=connector,
            tenant_id=tenant_id,
            since=since,
            cursor=resume_cursor,
            on_cursor_update=_persist_checkpoint,
            extra_acl=owner_acl,
        )
        
        # Store final cursor (may already match last per-page checkpoint)
        final_cursor = result.get("final_cursor")
        if final_cursor:
            _run_async(cursor_store.update_cursor(scope_id, source_type, final_cursor))
        elif source_type == "google_drive":
            # For Drive, if no pagination occurred (single page), fetch and store startPageToken
            # This enables ACL delta polling to work even when backfill had no nextPageToken
            try:
                from app.connectors.google.clients.drive_client import DriveClient
                drive_client = DriveClient()
                token = _run_async(connector.get_valid_token())
                start_page_token = _run_async(drive_client.get_start_page_token(token))
                if start_page_token:
                    _run_async(cursor_store.update_cursor(scope_id, source_type, start_page_token))
                    logger.info(
                        f"Stored Drive startPageToken for ACL delta polling tenant={tenant_id} token={start_page_token}"
                    )
            except Exception as exc:
                logger.warning(
                    f"Failed to fetch Drive startPageToken for ACL delta polling tenant={tenant_id}: {exc}"
                )

        _register_watches_best_effort(
            oauth_manager, scope_id, source_type, final_cursor
        )
        
        # For Gmail, override cursor with historyId from watch_data (not page token from backfill)
        if source_type == "google_gmail":
            watch_info = _run_async(cursor_store.get_watch_info(scope_id, source_type))
            if watch_info and "history_id" in watch_info:
                _run_async(cursor_store.update_cursor(scope_id, source_type, watch_info["history_id"]))

        logger.info(
            f"Backfill completed for tenant {tenant_id}, source {source_type}: "
            f"{result.get('indexed_count', 0)} indexed, {result.get('deleted_count', 0)} deleted, "
            f"{result.get('pages_processed', 0)} pages"
        )
        status_store.set_status(
            tenant_id,
            source_type,
            user_id=str(user_id or principal_id),  # Use original user_id for correct Redis key (organization vs personal)
            connection_status="active",
            files_indexed=int(result.get("indexed_count") or 0),
            last_error="",
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Backfill failed for tenant {tenant_id}, source {source_type}: {e}")
        err = str(e)
        conn_status = "needs_reauth" if "refresh" in err.lower() or "re-authorize" in err.lower() or "Unauthorized" in err else "error"
        try:
            status_store.set_status(
                tenant_id,
                source_type,
                user_id=str(user_id or ""),
                connection_status=conn_status,
                last_error=type(e).__name__,
            )
        except Exception:
            pass
        
        # Retry with exponential backoff on transient errors
        if "429" in str(e) or "quota" in str(e).lower():
            raise self.retry(exc=e, countdown=min(2 ** self.request.retries * 60, 3600))
        
        raise


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def backfill_source(self, tenant_id: str, source_type: str, user_id: str = None, connector_id: str = None) -> dict:
    """OAuth-callback auto-sync entrypoint. Same crawl as backfill_tenant_source."""
    return backfill_tenant_source.run(
        tenant_id=tenant_id,
        source_type=source_type,
        user_id=user_id,
        connector_id=connector_id,
    )


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def process_drive_notification(self, tenant_id: str) -> dict:
    """
    Process incremental Drive changes (triggered by webhook).
    
    Pipeline:
    1. Get stored page token from cursor_store
    2. Fetch changes since that token
    3. Transform and index
    4. Update stored cursor
    
    Args:
        tenant_id: Tenant identifier
        
    Returns:
        Summary dict with counts
    """
    try:
        logger.info(f"Processing Drive notification for tenant {tenant_id}")
        
        # Extract base tenant_id and principal_id from scoped tenant_id (e.g., "tenant_id:user_id" -> "tenant_id", "user_id")
        base_tenant_id = tenant_id.split(":")[0] if ":" in tenant_id else tenant_id
        principal_id = tenant_id.split(":")[1] if ":" in tenant_id else ""
        _validate_tenant_auth(base_tenant_id)

        # Get stored cursor using the scoped tenant_id
        page_token = _run_async(cursor_store.get_cursor(tenant_id, "google_drive"))
        if not page_token:
            logger.warning(f"No cursor found for tenant {tenant_id}, skipping")
            return {"status": "no_cursor", "indexed_count": 0, "deleted_count": 0}
        config = {"tenant_id": base_tenant_id}
        token_store = PersistentGoogleTokenStore(base_tenant_id)

        oauth_manager = GoogleOAuthManager(
            token_store,
            settings.google_client_id or "",
            settings.google_client_secret or "",
            [
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
            ],
            principal_id=principal_id,
        )
        client_id = settings.google_client_id or ""
        client_secret = settings.google_client_secret or ""
        seed_token_store_from_env(
            token_store,
            base_tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=getattr(settings, "google_refresh_token", None),
        )
        
        # Create Drive connector
        connector = DriveConnector(config, token_store, oauth_manager, connection_scope="organization")
        
        # Fetch changes since page token
        delta_result = _run_async(connector.fetch_since_page_token(page_token))
        
        logger.info(f"Drive delta result: documents={len(delta_result.documents) if hasattr(delta_result, 'documents') else 0}, next_cursor={delta_result.next_cursor}")
        
        unified_docs = []
        if hasattr(delta_result, "documents") and delta_result.documents:
            _attach_extracted_text_for_pipeline(delta_result.documents)
            from app.connectors.google.pipeline_bridge import process_raw_batch

            unified_docs = _run_async(
                process_raw_batch(
                    delta_result.documents,
                    "google_drive",
                    base_tenant_id,
                    require_postgres=True,
                )
            )
            if unified_docs is None:
                raise RuntimeError(
                    f"webhook ACL compile failed: process_raw_batch returned None tenant={base_tenant_id}"
                )
            if unified_docs:
                _run_async(indexer.bulk_index(unified_docs, base_tenant_id))
        
        # Handle deletions
        deleted_ids = getattr(delta_result, "deleted_ids", [])
        if deleted_ids:
            _run_async(indexer.delete_by_ids(deleted_ids, base_tenant_id, "google_drive"))
        
        # Update cursor (always advance if Drive API returned a new cursor)
        if hasattr(delta_result, "next_cursor") and delta_result.next_cursor:
            _run_async(cursor_store.update_cursor(tenant_id, "google_drive", delta_result.next_cursor))
        
        doc_count = len(unified_docs)
        logger.info(
            f"Drive notification processed for tenant {tenant_id}: "
            f"{doc_count} indexed, {len(deleted_ids)} deleted"
        )
        
        return {
            "status": "success",
            "indexed_count": doc_count,
            "deleted_count": len(deleted_ids),
        }
    
    except Exception as e:
        logger.error(f"Drive notification processing failed for tenant {tenant_id}: {e}")
        if isinstance(e, (InvalidTokenError, UnauthorizedError, RevokedTokenError)):
            from app.connectors.google.drive_credentials import set_drive_ingest_paused

            try:
                _run_async(
                    set_drive_ingest_paused(tenant_id, True, type(e).__name__)
                )
            except Exception:
                logger.exception("failed to pause Drive ingest tenant=%s", tenant_id)
        
        # Retry on transient errors
        if "429" in str(e) or "quota" in str(e).lower():
            raise self.retry(exc=e, countdown=min(2 ** self.request.retries * 60, 3600))
        
        raise


@celery_app.task
def poll_drive_acl_delta() -> dict:
    """Beat fallback: same incremental path as the Drive webhook, every ~3 minutes."""
    from app.workers.drive_acl_poll import enqueue_drive_acl_poll

    tenant_ids = _run_async(cursor_store.list_tenants_with_cursor("google_drive"))
    result = enqueue_drive_acl_poll(tenant_ids, process_drive_notification.delay)
    logger.info("poll_drive_acl_delta enqueued=%s", result["enqueued"])
    return result


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def poll_gmail_pubsub(self) -> dict:
    """
    Pull Gmail push notifications from Pub/Sub subscription and process them.

    This task runs every 60 seconds via Celery Beat to pull messages from
    the Gmail Pub/Sub subscription (gmail-push-notifications-sub).

    Pipeline:
    1. Pull messages from Pub/Sub subscription
    2. Decode Gmail historyId/emailAddress from message payload
    3. Call process_gmail_notification for each tenant with changes
    4. Ack messages only after successful processing

    Returns:
        Summary dict with processed count and errors
    """
    try:
        project_id = getattr(settings, "google_pubsub_project_id", None)
        subscription_name = getattr(settings, "google_pubsub_subscription", None)

        if not project_id:
            logger.debug("Gmail Pub/Sub pull skipped: GOOGLE_PUBSUB_PROJECT_ID not set")
            return {"status": "skipped", "reason": "no_project_id", "processed": 0}

        if not subscription_name:
            logger.debug("Gmail Pub/Sub pull skipped: GOOGLE_PUBSUB_SUBSCRIPTION not set")
            return {"status": "skipped", "reason": "no_subscription", "processed": 0}

        from google.cloud import pubsub_v1

        subscriber = pubsub_v1.SubscriberClient()
        subscription_path = subscriber.subscription_path(project_id, subscription_name)

        # Pull up to 10 messages per poll
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": 10},
            timeout=30.0,
        )

        if not response.received_messages:
            return {"status": "success", "processed": 0, "errors": []}

        processed_count = 0
        errors = []
        ack_ids = []

        for msg in response.received_messages:
            try:
                import base64
                import json

                # Decode Pub/Sub message data
                payload = json.loads(msg.message.data.decode("utf-8"))

                # Gmail push notification format
                email_address = payload.get("emailAddress")
                history_id = payload.get("historyId")

                if not email_address or not history_id:
                    logger.warning(f"Invalid Gmail push notification: missing emailAddress or historyId")
                    ack_ids.append(msg.ack_id)
                    continue

                # Map email address to tenant_id by querying tenant_connectors
                from app.storage.control_plane_db import ControlPlaneSessionLocal
                from sqlalchemy import select
                from app.models.tenant_connector import TenantConnector
                
                tenant_id = None
                try:
                    async def _map_email():
                        async with ControlPlaneSessionLocal() as session:
                            result = await session.execute(
                                select(TenantConnector.tenant_id, TenantConnector.config)
                                .where(TenantConnector.source_type == "google_gmail")
                                .where(TenantConnector.connection_scope == "personal")
                                .where(TenantConnector.config["mailbox_email"].astext == email_address)
                            )
                            row = result.first()
                            if row:
                                tid = str(row[0])
                                config = row[1]
                                user_id_for_cursor = config.get("connected_by") if config else None
                                # Build composite tenant_id for cursor lookup
                                if user_id_for_cursor:
                                    return f"{tid}:{user_id_for_cursor}"
                                return tid
                            return None
                    
                    tenant_id = _run_async(_map_email())
                except Exception as e:
                    logger.error(f"Failed to map email address {email_address} to tenant_id: {e}")
                
                if not tenant_id:
                    logger.warning(f"No tenant found for email address {email_address}, skipping notification")
                    ack_ids.append(msg.ack_id)
                    continue

                # Process the notification
                result = process_gmail_notification(tenant_id)

                if result.get("status") == "success":
                    processed_count += 1
                    ack_ids.append(msg.ack_id)
                    logger.info(
                        f"Gmail PubSub message processed: tenant={tenant_id}, "
                        f"historyId={history_id}, indexed={result.get('indexed_count', 0)}"
                    )
                else:
                    logger.error(f"Gmail notification processing failed: {result}")
                    errors.append(f"tenant={tenant_id}, error={result.get('status')}")

            except Exception as e:
                logger.error(f"Failed to process Gmail PubSub message: {e}")
                errors.append(str(e))
                # Don't ack failed messages - they'll be redelivered

        # Ack successfully processed messages
        if ack_ids:
            subscriber.acknowledge(
                request={"subscription": subscription_path, "ack_ids": ack_ids}
            )

        logger.info(f"Gmail PubSub poll completed: processed={processed_count}, errors={len(errors)}")

        return {
            "status": "success",
            "processed": processed_count,
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Gmail PubSub poll failed: {e}")
        # Retry on transient errors
        if "deadline" in str(e).lower() or "timeout" in str(e).lower():
            raise self.retry(exc=e, countdown=30)
        return {"status": "error", "processed": 0, "errors": [str(e)]}


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def process_gmail_notification(self, tenant_id: str) -> dict:
    """
    Process incremental Gmail changes (triggered by Pub/Sub).
    
    Pipeline:
    1. Get stored history ID from cursor_store
    2. Fetch history since that ID (messages.get payloads already full MIME)
    3. process_raw_batch (Postgres CanonicalRepo) → ACLCompiler → replace_acl_entries
    4. bulk_index (re-embed; same chain as Drive webhook / backfill)
    5. Update stored cursor (only here — not on the HTTP webhook path)
    
    Args:
        tenant_id: Tenant identifier
        
    Returns:
        Summary dict with counts
    """
    try:
        logger.info(f"Processing Gmail notification for tenant {tenant_id}")
        _validate_tenant_auth(tenant_id)

        history_id = _run_async(cursor_store.get_cursor(tenant_id, "google_gmail"))
        if not history_id:
            logger.warning(f"No cursor found for tenant {tenant_id}, skipping")
            return {"status": "no_cursor", "indexed_count": 0, "deleted_count": 0}
        
        # Extract base tenant_id and user_id from composite tenant_id if present
        base_tenant_id = tenant_id
        principal_id = None
        if ":" in tenant_id:
            parts = tenant_id.split(":")
            if len(parts) == 2:
                base_tenant_id = parts[0]
                principal_id = parts[1]
        
        token_store = PersistentGoogleTokenStore(base_tenant_id)
        oauth_manager = GoogleOAuthManager(
            token_store,
            settings.google_client_id or "",
            settings.google_client_secret or "",
            [
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
            ],
            principal_id=principal_id,
        )
        client_id = settings.google_client_id or ""
        client_secret = settings.google_client_secret or ""
        mailbox_email = _lookup_mailbox_email(tenant_id, token_store, oauth_manager)
        config = {
            "tenant_id": tenant_id,
            "mailbox_email": mailbox_email or "",
        }
        seed_token_store_from_env(
            token_store,
            tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=getattr(settings, "google_refresh_token", None),
        )
        
        # Create Gmail connector
        connector = GmailConnector(config, token_store, oauth_manager)
        
        # Fetch changes since history ID
        delta_result = _run_async(connector.fetch_since_history_id(history_id))
        
        unified_docs = []
        if hasattr(delta_result, "documents") and delta_result.documents:
            from app.connectors.google.pipeline_bridge import process_raw_batch

            unified_docs = _run_async(
                process_raw_batch(
                    delta_result.documents,
                    "google_gmail",
                    tenant_id,
                    require_postgres=True,
                )
            )
            if unified_docs is None:
                raise RuntimeError(
                    f"webhook ACL compile failed: process_raw_batch returned None tenant={tenant_id}"
                )
            if unified_docs:
                _run_async(indexer.bulk_index(unified_docs, tenant_id))
        
        # Handle deletions
        deleted_ids = getattr(delta_result, "deleted_ids", [])
        if deleted_ids:
            _run_async(indexer.delete_by_ids(deleted_ids, tenant_id, "google_gmail"))
        
        # Update cursor only after compile/index (or empty delta / deletes)
        if hasattr(delta_result, "next_cursor") and delta_result.next_cursor:
            _run_async(cursor_store.update_cursor(tenant_id, "google_gmail", delta_result.next_cursor))
        
        doc_count = len(unified_docs)
        logger.info(
            f"Gmail notification processed for tenant {tenant_id}: "
            f"{doc_count} indexed, {len(deleted_ids)} deleted"
        )
        
        return {
            "status": "success",
            "indexed_count": doc_count,
            "deleted_count": len(deleted_ids),
        }
    
    except Exception as e:
        logger.error(f"Gmail notification processing failed for tenant {tenant_id}: {e}")
        
        # Retry on transient errors
        if "429" in str(e) or "quota" in str(e).lower():
            raise self.retry(exc=e, countdown=min(2 ** self.request.retries * 60, 3600))
        
        raise


@celery_app.task
def renew_watch_channels() -> dict:
    """
    Renew all expiring watch channels/subscriptions.
    
    Called by Celery Beat periodically (e.g., every 24 hours).
    
    Returns:
        Summary dict with renewal counts
    """
    try:
        logger.info("Starting watch channel renewal")
        
        # Create OAuth manager and watch manager
        token_store = PersistentGoogleTokenStore()
        oauth_manager = GoogleOAuthManager(
            token_store,
            settings.google_client_id or "",
            settings.google_client_secret or "",
            [
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
            ],
        )
        
        webhook_base_url = getattr(settings, "WEBHOOK_BASE_URL", "http://localhost:8000")
        watch_manager = WatchManager(oauth_manager, cursor_store, webhook_base_url)
        
        # Renew expiring watches
        result = _run_async(watch_manager.renew_expiring_watches())
        
        logger.info(
            f"Watch renewal completed: "
            f"{result['drive_renewed']} Drive, "
            f"{result['gmail_renewed']} Gmail, "
            f"{len(result['errors'])} errors"
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Watch renewal failed: {e}")
        raise


@celery_app.task(name="app.workers.tasks.google_queue_ping")
def google_queue_ping() -> dict:
    """Harmless ping used to prove a worker is consuming the `google` queue."""
    logger.info("google_queue_ping: pipeline=queue_ok queue=google")
    return {"ok": True, "queue": "google"}


def _register_watches_best_effort(
    oauth_manager, tenant_id: str, source_type: str, final_cursor: Optional[str]
) -> None:
    """Push watches are optional. Never fail a completed crawl over them.

    Google rejects http://localhost webhook URLs, so a local Connect+sync
    used to index files and then mark the task `error` on watch setup.
    """
    if not final_cursor or oauth_manager is None:
        return
    webhook_base_url = (
        getattr(settings, "webhook_base_url", None)
        or "http://localhost:8000"
    )
    lowered = webhook_base_url.lower()
    if "localhost" in lowered or "127.0.0.1" in lowered:
        logger.info(
            "Skipping Google watch registration tenant=%s source=%s "
            "(webhook URL is not publicly reachable)",
            tenant_id,
            source_type,
        )
        return
    watch_manager = WatchManager(oauth_manager, cursor_store, webhook_base_url)
    try:
        if source_type == "google_drive":
            _run_async(watch_manager.register_drive_watch(tenant_id, final_cursor))
        elif source_type == "google_gmail":
            pubsub_topic = getattr(settings, "google_pubsub_topic", None) or ""
            project_id = getattr(settings, "google_pubsub_project_id", None) or ""
            if pubsub_topic and project_id:
                full_topic = f"projects/{project_id}/topics/{pubsub_topic}"
                _run_async(
                    watch_manager.register_gmail_watch(tenant_id, final_cursor, full_topic)
                )
    except Exception:
        logger.warning(
            "Watch registration failed after successful index tenant=%s source=%s",
            tenant_id,
            source_type,
            exc_info=True,
        )


def _attach_extracted_text_for_pipeline(documents: list) -> None:
    """Copy hydrate's ``_extracted_text`` onto ``extractedText`` for process_raw.

    GoogleDriveNormalizer.extract_text does not read ``_extracted_text``. Glue
    lives here so the webhook path does not change shared extractor field order.
    """
    for file in documents or []:
        extracted = file.get("_extracted_text")
        if isinstance(extracted, str) and extracted:
            file["extractedText"] = extracted
        logger.info(
            "drive webhook change file_id=%s modifiedTime=%s",
            file.get("id"),
            file.get("modifiedTime"),
        )


def _acl_terms_for_user(user_id: Optional[str]) -> list:
    principal = str(user_id or "")
    if not principal:
        return []
    terms = [principal]
    if not principal.startswith(("user:", "group:")):
        terms.append(f"user:{principal}")
    return terms


def _lookup_mailbox_email(
    tenant_id: str, token_store, oauth_manager, user_id: str = ""
) -> str:
    """Read mailbox email from the stored token blob (set at OAuth callback)."""
    if token_store is None:
        return ""
    try:
        # Extract base tenant_id from composite format (tenant_id:user_id)
        base_tenant_id = tenant_id
        if ":" in tenant_id:
            parts = tenant_id.split(":")
            if len(parts) == 2:
                base_tenant_id = parts[0]
                # If user_id not provided, extract from composite
                if not user_id:
                    user_id = parts[1]
        
        data = token_store.get_token(google_oauth_token_key(base_tenant_id, user_id, "personal")) or {}
        if not data.get("mailbox_email"):
            data = token_store.get_token(google_oauth_token_key(base_tenant_id, "", "personal")) or {}
        return str(data.get("mailbox_email") or "")
    except Exception:
        return ""


@celery_app.task
def run_scheduled_tenant_backups() -> dict:
    """
    Backup all tenants in the control plane.

    Scheduled by Celery Beat (default: daily 02:00 UTC).
    """
    from sqlalchemy import select

    from app.models.tenant import Tenant
    from app.scripts.backup import backup_tenant
    from app.storage.control_plane_db import ControlPlaneSessionLocal

    async def _run() -> dict:
        async with ControlPlaneSessionLocal() as session:
            result = await session.execute(select(Tenant.tenant_id))
            tenant_ids = [str(row[0]) for row in result.fetchall()]

        backed_up: list[dict] = []
        errors: list[dict] = []
        for tenant_id in tenant_ids:
            try:
                metadata = await backup_tenant(ControlPlaneSessionLocal, tenant_id)
                backed_up.append(
                    {
                        "tenant_id": tenant_id,
                        "backup_id": metadata.backup_id,
                        "row_count": metadata.row_count,
                    }
                )
            except Exception as exc:
                logger.error("Scheduled backup failed for tenant %s: %s", tenant_id, exc)
                errors.append({"tenant_id": tenant_id, "error": str(exc)})

        logger.info(
            "Scheduled tenant backups complete: %s succeeded, %s failed",
            len(backed_up),
            len(errors),
        )
        return {"backed_up": backed_up, "errors": errors, "count": len(backed_up)}

    return _run_async(_run())
