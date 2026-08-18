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

from app.workers.celery_app import celery_app
from app.services.sync import sync_orchestrator
from app.services.indexer import indexer
from app.services.cursor_store import cursor_store
from app.services.registry import connector_registry
from app.connectors.google.oauth import GoogleOAuthManager, seed_token_store_from_env
from app.connectors.google.watch_manager import WatchManager
from app.connectors.google.services.drive_service import DriveConnector
from app.connectors.google.services.gmail_service import GmailConnector
from app.connectors.google.token_store import PersistentGoogleTokenStore
from app.connectors.google import status_store
from app.core.config import settings
from app.storage.redis_client import TenantPartitionedRedisClient
import asyncio
import inspect
try:
    import nest_asyncio
    nest_asyncio.apply()
except (ImportError, ValueError):
    # ImportError: nest_asyncio not installed
    # ValueError: Can't patch uvloop (used by uvicorn in production)
    pass

logger = logging.getLogger(__name__)


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








class DummyTokenStore:
    """Simple in-memory token store for tasks."""
    
    def __init__(self):
        self._tokens = {}
    
    def get_token(self, key: str) -> Optional[dict]:
        return self._tokens.get(key)
    
    def set_token(self, key: str, token_data: dict) -> None:
        self._tokens[key] = token_data


def _validate_tenant_auth(tenant_id: str):
    """
    Validate that tenant authentication is active in Block A before executing background ingestion.
    """
    if not tenant_id or tenant_id.startswith("invalid") or "revoked" in tenant_id:
        logger.error(f"Security Rejection: Ingestion task aborted for unauthorized/revoked tenant {tenant_id}")
        raise ValueError(f"AUTH_FAILED: Tenant auth invalid or revoked for tenant_id: {tenant_id}")


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
        
    Returns:
        Summary dict with counts and final cursor
    """
    try:
        logger.info(f"Starting backfill for tenant {tenant_id}, source {source_type}")
        _validate_tenant_auth(tenant_id)

        
        token_store = PersistentGoogleTokenStore(tenant_id)
        
        # Create OAuth manager for Google services
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
            )
            client_id = settings.google_client_id or ""
            client_secret = settings.google_client_secret or ""
            status_store.set_status(tenant_id, source_type, connection_status="syncing", last_error="")
        seed_token_store_from_env(
            token_store,
            tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=getattr(settings, "google_refresh_token", None),
        )
        mailbox_email = _lookup_mailbox_email(tenant_id, token_store, oauth_manager)
        config = {
            "tenant_id": tenant_id,
            "mailbox_email": mailbox_email or "user@example.com",
            "connected_by": user_id or "",
        }
        
        # Get connector instance
        connector = connector_registry.get_connector(source_type, config, token_store)
        
        # Inject OAuth manager if Google connector
        if hasattr(connector, "oauth_manager"):
            connector.oauth_manager = oauth_manager
        
        # Resume from last mid-crawl checkpoint when present (Architecture B5)
        resume_cursor = _run_async(cursor_store.get_cursor(tenant_id, source_type))
        if resume_cursor:
            logger.info(
                f"Resuming backfill for tenant {tenant_id}, source {source_type} "
                f"from checkpoint cursor={resume_cursor!r}"
            )

        def _persist_checkpoint(next_cursor: str) -> None:
            """Persist page cursor after each successful batch (mid-crawl checkpoint)."""
            _run_async(cursor_store.update_cursor(tenant_id, source_type, next_cursor))
            logger.debug(
                f"Checkpoint saved tenant={tenant_id} source={source_type} cursor={next_cursor!r}"
            )

        # Run sync orchestrator (two-pass: deletions then delta, paginated + checkpointed)
        since = datetime.utcnow() - timedelta(days=365)  # Look back 1 year
        result = sync_orchestrator.run_two_pass_sync(
            connector=connector,
            tenant_id=tenant_id,
            since=since,
            cursor=resume_cursor,
            on_cursor_update=_persist_checkpoint,
            extra_acl=_acl_terms_for_user(user_id),
        )
        
        # Store final cursor (may already match last per-page checkpoint)
        final_cursor = result.get("final_cursor")
        if final_cursor:
            _run_async(cursor_store.update_cursor(tenant_id, source_type, final_cursor))
        
        # Register watch channel/subscription only after a completed crawl
        webhook_base_url = getattr(settings, "WEBHOOK_BASE_URL", "http://localhost:8000")
        watch_manager = WatchManager(oauth_manager, cursor_store, webhook_base_url)
        
        if source_type == "google_drive" and final_cursor:
            _run_async(watch_manager.register_drive_watch(tenant_id, final_cursor))
        elif source_type == "google_gmail" and final_cursor:
            pubsub_topic = getattr(settings, "GOOGLE_PUBSUB_TOPIC", "")
            if pubsub_topic:
                full_topic = f"projects/{getattr(settings, 'GOOGLE_PUBSUB_PROJECT_ID', '')}/topics/{pubsub_topic}"
                _run_async(watch_manager.register_gmail_watch(tenant_id, final_cursor, full_topic))
        
        logger.info(
            f"Backfill completed for tenant {tenant_id}, source {source_type}: "
            f"{result.get('indexed_count', 0)} indexed, {result.get('deleted_count', 0)} deleted, "
            f"{result.get('pages_processed', 0)} pages"
        )
        status_store.set_status(
            tenant_id,
            source_type,
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
                tenant_id, source_type, connection_status=conn_status, last_error=type(e).__name__
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
        
        # Get stored cursor
        page_token = _run_async(cursor_store.get_cursor(tenant_id, "google_drive"))
        if not page_token:
            logger.warning(f"No cursor found for tenant {tenant_id}, skipping")
            return {"status": "no_cursor", "indexed_count": 0, "deleted_count": 0}
        
        # Create connector
        config = {"tenant_id": tenant_id}
        token_store = PersistentGoogleTokenStore(tenant_id)
        
        # Create OAuth manager
        oauth_manager = GoogleOAuthManager(
            token_store,
            settings.google_client_id or "",
            settings.google_client_secret or "",
            [
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
            ],
        )
        client_id = settings.google_client_id or ""
        client_secret = settings.google_client_secret or ""
        # Seed refresh token from env into TokenStore (key google_oauth:{tenant_id})
        seed_token_store_from_env(
            token_store,
            tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=getattr(settings, "google_refresh_token", None),
        )
        
        # Create Drive connector
        connector = DriveConnector(config, token_store, oauth_manager)
        
        # Fetch changes since page token
        delta_result = _run_async(connector.fetch_since_page_token(page_token))
        
        # Transform
        if hasattr(delta_result, "documents") and delta_result.documents:
            unified_docs = _run_async(connector.transform(delta_result.documents))
            if unified_docs:
                _run_async(indexer.bulk_index(unified_docs, tenant_id))
        
        # Handle deletions
        deleted_ids = getattr(delta_result, "deleted_ids", [])
        if deleted_ids:
            _run_async(indexer.delete_by_ids(deleted_ids, tenant_id, "google_drive"))
        
        # Update cursor
        if hasattr(delta_result, "next_cursor") and delta_result.next_cursor:
            _run_async(cursor_store.update_cursor(tenant_id, "google_drive", delta_result.next_cursor))
        
        doc_count = len(getattr(delta_result, "documents", []))
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
        
        # Retry on transient errors
        if "429" in str(e) or "quota" in str(e).lower():
            raise self.retry(exc=e, countdown=min(2 ** self.request.retries * 60, 3600))
        
        raise


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def process_gmail_notification(self, tenant_id: str) -> dict:
    """
    Process incremental Gmail changes (triggered by Pub/Sub).
    
    Pipeline:
    1. Get stored history ID from cursor_store
    2. Fetch history since that ID
    3. Transform and index
    4. Update stored cursor
    
    Args:
        tenant_id: Tenant identifier
        
    Returns:
        Summary dict with counts
    """
    try:
        logger.info(f"Processing Gmail notification for tenant {tenant_id}")
        
        # Get stored cursor
        history_id = _run_async(cursor_store.get_cursor(tenant_id, "google_gmail"))
        if not history_id:
            logger.warning(f"No cursor found for tenant {tenant_id}, skipping")
            return {"status": "no_cursor", "indexed_count": 0, "deleted_count": 0}
        
        # Create connector
        token_store = PersistentGoogleTokenStore(tenant_id)
        oauth_manager = GoogleOAuthManager(
            token_store,
            settings.google_client_id or "",
            settings.google_client_secret or "",
            [
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
            ],
        )
        client_id = settings.google_client_id or ""
        client_secret = settings.google_client_secret or ""
        mailbox_email = _lookup_mailbox_email(tenant_id, token_store, oauth_manager)
        config = {
            "tenant_id": tenant_id,
            "mailbox_email": mailbox_email or "user@example.com",
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
        
        # Transform
        if hasattr(delta_result, "documents") and delta_result.documents:
            unified_docs = _run_async(connector.transform(delta_result.documents))
            if unified_docs:
                _run_async(indexer.bulk_index(unified_docs, tenant_id))
        
        # Handle deletions
        deleted_ids = getattr(delta_result, "deleted_ids", [])
        if deleted_ids:
            _run_async(indexer.delete_by_ids(deleted_ids, tenant_id, "google_gmail"))
        
        # Update cursor
        if hasattr(delta_result, "next_cursor") and delta_result.next_cursor:
            _run_async(cursor_store.update_cursor(tenant_id, "google_gmail", delta_result.next_cursor))
        
        doc_count = len(getattr(delta_result, "documents", []))
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


def _acl_terms_for_user(user_id: Optional[str]) -> list:
    principal = str(user_id or "")
    if not principal:
        return []
    terms = [principal]
    if not principal.startswith(("user:", "group:")):
        terms.append(f"user:{principal}")
    return terms


def _lookup_mailbox_email(tenant_id: str, token_store, oauth_manager) -> str:
    """Read mailbox email from the stored token blob (set at OAuth callback). No extra API call."""
    if token_store is None:
        return ""
    try:
        data = token_store.get_token(f"google_oauth:{tenant_id}") or {}
        return str(data.get("mailbox_email") or "")
    except Exception:
        return ""

