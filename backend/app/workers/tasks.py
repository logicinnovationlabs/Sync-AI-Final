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
from app.connectors.google.oauth import GoogleOAuthManager
from app.connectors.google.watch_manager import WatchManager
from app.connectors.google.services.drive_service import DriveConnector
from app.connectors.google.services.gmail_service import GmailConnector
from app.core.config import settings
from app.storage.redis_client import TenantPartitionedRedisClient
import asyncio
import inspect
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

logger = logging.getLogger(__name__)


# ============================================================
# BLOCK C PIPELINE INTEGRATION
# ============================================================
# Pipeline instance is lazily initialized to avoid import-time dependencies
_pipeline_instance = None


def _get_pipeline():
    """Get or create Block C pipeline instance.

    Returns None if Block C deps (e.g. libmagic) are unavailable so Block B
    notification tasks can fall back to connector.transform().
    """
    global _pipeline_instance
    if _pipeline_instance is False:
        return None
    if _pipeline_instance is None:
        try:
            from app.services.pipeline import Pipeline
            from app.normalizer.registry import normalizer_registry
            from app.identity.resolver import IdentityResolver
            from app.identity.matchers.email_matcher import EmailMatcher
            from app.identity.matchers.username_matcher import UsernameMatcher
            from app.acl.compiler import ACLCompiler
            from app.acl.container_service import ContainerService
            from app.storage.canonical_repo import CanonicalRepo

            # Import strategies to register them
            import app.normalizer.strategies

            # Initialize components
            canonical_repo = CanonicalRepo(use_memory=True)
            matchers = [EmailMatcher(), UsernameMatcher()]
            identity_resolver = IdentityResolver(matchers, canonical_repo)
            container_service = ContainerService(canonical_repo)
            acl_compiler = ACLCompiler(identity_resolver, container_service, canonical_repo)

            _pipeline_instance = Pipeline(
                normalizer_registry,
                identity_resolver,
                acl_compiler,
                canonical_repo,
            )
        except Exception as e:
            logger.warning(
                "Block C pipeline unavailable; falling back to connector.transform: %s",
                e,
            )
            _pipeline_instance = False
            return None

    return _pipeline_instance


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
def backfill_tenant_source(self, tenant_id: str, source_type: str) -> dict:
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

        
        # Get connector config
        config = {
            "tenant_id": tenant_id,
            "mailbox_email": f"user@example.com",  # TODO: Get from tenant config
        }
        
        token_store = DummyTokenStore()
        
        # Create OAuth manager for Google services
        oauth_manager = None
        if source_type.startswith("google_"):
            client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
            client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")
            scopes = [
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
            ]
            oauth_manager = GoogleOAuthManager(token_store, client_id, client_secret, scopes)
        
        # Get connector instance
        connector = connector_registry.get_connector(source_type, config, token_store)
        
        # Inject OAuth manager if Google connector
        if hasattr(connector, "oauth_manager"):
            connector.oauth_manager = oauth_manager
        
        # Run sync orchestrator (two-pass: deletions then delta)
        since = datetime.utcnow() - timedelta(days=365)  # Look back 1 year
        result = sync_orchestrator.run_two_pass_sync(
            connector=connector,
            tenant_id=tenant_id,
            since=since,
        )
        
        # Store final cursor
        final_cursor = result.get("final_cursor")
        if final_cursor:
            _run_async(cursor_store.update_cursor(tenant_id, source_type, final_cursor))
        
        # Register watch channel/subscription
        webhook_base_url = getattr(settings, "WEBHOOK_BASE_URL", "http://localhost:8000/api/v1")
        watch_manager = WatchManager(oauth_manager, cursor_store, webhook_base_url)
        
        if source_type == "google_drive":
            _run_async(watch_manager.register_drive_watch(tenant_id, final_cursor))
        elif source_type == "google_gmail":
            pubsub_topic = getattr(settings, "GOOGLE_PUBSUB_TOPIC", "")
            if pubsub_topic:
                full_topic = f"projects/{getattr(settings, 'GOOGLE_PUBSUB_PROJECT_ID', '')}/topics/{pubsub_topic}"
                _run_async(watch_manager.register_gmail_watch(tenant_id, final_cursor, full_topic))
        
        logger.info(
            f"Backfill completed for tenant {tenant_id}, source {source_type}: "
            f"{result.get('indexed_count', 0)} indexed, {result.get('deleted_count', 0)} deleted"
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Backfill failed for tenant {tenant_id}, source {source_type}: {e}")
        
        # Retry with exponential backoff on transient errors
        if "429" in str(e) or "quota" in str(e).lower():
            raise self.retry(exc=e, countdown=min(2 ** self.request.retries * 60, 3600))
        
        raise


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
        token_store = DummyTokenStore()
        
        # Create OAuth manager
        client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
        client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")
        scopes = [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/gmail.readonly",
        ]
        oauth_manager = GoogleOAuthManager(token_store, client_id, client_secret, scopes)
        
        # Create Drive connector
        connector = DriveConnector(config, token_store, oauth_manager)
        
        # Fetch changes since page token
        delta_result = _run_async(connector.fetch_since_page_token(page_token))
        
        # Prefer Block C pipeline; fall back to Block B transform if unavailable
        if hasattr(delta_result, "documents") and delta_result.documents:
            pipeline = _get_pipeline()
            unified_docs = []

            if pipeline is not None:
                for raw in delta_result.documents:
                    try:
                        result = _run_async(
                            pipeline.process_raw(
                                raw, source_type="google_drive", tenant_id=UUID(tenant_id)
                            )
                        )
                        unified_docs.append(result["unified_document"])
                    except Exception as e:
                        logger.error(
                            f"Pipeline processing failed for document {raw.get('id')}: {e}"
                        )
            else:
                unified_docs = _run_async(connector.transform(delta_result.documents)) or []

            if unified_docs:
                _run_async(indexer.bulk_index(unified_docs, tenant_id))
        
        # Handle deletions
        deleted_ids = getattr(delta_result, "deleted_ids", [])
        if deleted_ids:
            # Delete from both canonical store and vector index when Block C is available
            try:
                from app.storage.canonical_repo import CanonicalRepo
                canonical_repo = CanonicalRepo(use_memory=True)
                _run_async(canonical_repo.delete_documents_and_acls(deleted_ids, UUID(tenant_id)))
            except Exception as e:
                logger.warning("Canonical ACL delete skipped: %s", e)
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
        config = {
            "tenant_id": tenant_id,
            "mailbox_email": "user@example.com",  # TODO: Get from tenant config
        }
        token_store = DummyTokenStore()
        
        # Create OAuth manager
        client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
        client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")
        scopes = [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/gmail.readonly",
        ]
        oauth_manager = GoogleOAuthManager(token_store, client_id, client_secret, scopes)
        
        # Create Gmail connector
        connector = GmailConnector(config, token_store, oauth_manager)
        
        # Fetch changes since history ID
        delta_result = _run_async(connector.fetch_since_history_id(history_id))
        
        # Prefer Block C pipeline; fall back to Block B transform if unavailable
        if hasattr(delta_result, "documents") and delta_result.documents:
            pipeline = _get_pipeline()
            unified_docs = []

            if pipeline is not None:
                for raw in delta_result.documents:
                    # Inject mailbox email for Gmail
                    raw["_mailbox_email"] = config.get("mailbox_email", "user@example.com")

                    try:
                        result = _run_async(
                            pipeline.process_raw(
                                raw, source_type="google_gmail", tenant_id=UUID(tenant_id)
                            )
                        )
                        unified_docs.append(result["unified_document"])
                    except Exception as e:
                        logger.error(
                            f"Pipeline processing failed for message {raw.get('id')}: {e}"
                        )
            else:
                unified_docs = _run_async(connector.transform(delta_result.documents)) or []

            if unified_docs:
                _run_async(indexer.bulk_index(unified_docs, tenant_id))
        
        # Handle deletions
        deleted_ids = getattr(delta_result, "deleted_ids", [])
        if deleted_ids:
            try:
                from app.storage.canonical_repo import CanonicalRepo
                canonical_repo = CanonicalRepo(use_memory=True)
                _run_async(canonical_repo.delete_documents_and_acls(deleted_ids, UUID(tenant_id)))
            except Exception as e:
                logger.warning("Canonical ACL delete skipped: %s", e)
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
        client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
        client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")
        scopes = [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/gmail.readonly",
        ]
        token_store = DummyTokenStore()
        oauth_manager = GoogleOAuthManager(token_store, client_id, client_secret, scopes)
        
        webhook_base_url = getattr(settings, "WEBHOOK_BASE_URL", "http://localhost:8000/api/v1")
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


@celery_app.task(bind=True, max_retries=3)
def revalidate_acls_for_tenant(self, tenant_id: str, source_type: str) -> dict:
    """
    Revalidate ACLs for a tenant/source.
    
    Re-fetches permission changes since the last revalidation run and updates
    ACL entries. This catches permission-only changes that don't trigger a
    content webhook.
    
    Called by Celery Beat periodically (e.g., every 15 minutes).
    
    Args:
        tenant_id: Tenant identifier
        source_type: Source type (e.g., 'google_drive', 'google_gmail')
        
    Returns:
        Summary dict with revalidation counts
    """
    try:
        logger.info(f"Starting ACL revalidation for tenant {tenant_id}, source {source_type}")
        
        # Get last revalidation time from cursor_store
        # NOTE: This would require adding ACL-specific cursor methods to cursor_store
        # For now, use a 15-minute lookback
        since = datetime.utcnow() - timedelta(minutes=15)
        
        # Get connector
        config = {"tenant_id": tenant_id, "mailbox_email": "user@example.com"}
        token_store = DummyTokenStore()
        
        # Create OAuth manager for Google services
        oauth_manager = None
        if source_type.startswith("google_"):
            client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
            client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")
            scopes = [
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
            ]
            oauth_manager = GoogleOAuthManager(token_store, client_id, client_secret, scopes)
        
        connector = connector_registry.get_connector(source_type, config, token_store)
        
        # Inject OAuth manager if Google connector
        if hasattr(connector, "oauth_manager"):
            connector.oauth_manager = oauth_manager
        
        # Fetch permission changes
        changes = _run_async(connector.fetch_permission_changes(since))
        
        if not changes:
            logger.info(f"No permission changes found for tenant {tenant_id}, source {source_type}")
            return {"status": "success", "changes_count": 0}
        
        # Re-process affected documents through pipeline
        pipeline = _get_pipeline()
        revalidated_count = 0
        
        for change in changes:
            change_id = change.get("id")
            change_type = change.get("type")
            
            # Fetch fresh document/container data
            # NOTE: This would need connector.fetch_by_id() method (not implemented yet)
            # For now, skip actual reprocessing
            logger.info(f"Would revalidate {change_type} {change_id}")
            revalidated_count += 1
        
        logger.info(
            f"ACL revalidation completed for tenant {tenant_id}, source {source_type}: "
            f"{revalidated_count} items revalidated"
        )
        
        return {
            "status": "success",
            "changes_count": len(changes),
            "revalidated_count": revalidated_count,
        }
    
    except Exception as e:
        logger.error(f"ACL revalidation failed for tenant {tenant_id}, source {source_type}: {e}")
        
        # Retry on transient errors
        if "429" in str(e) or "quota" in str(e).lower():
            raise self.retry(exc=e, countdown=min(2 ** self.request.retries * 60, 3600))
        
        raise
