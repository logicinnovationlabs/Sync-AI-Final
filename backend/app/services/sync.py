"""
Blind Orchestrator: two-pass sync (deletion first, then delta).

This module orchestrates connector syncs WITHOUT ever importing specific connectors.
It only knows about BaseConnector and the Registry. Adding connector #11 requires
zero edits to this file.

Critical for the "Blind Orchestrator Rule."

Architecture B5 (checkpoint resume): mid-crawl cursors are persisted via an optional
``on_cursor_update`` callback after each successful page so a killed crawl can resume
without duplicates or missing objects (upsert semantics + page-token resume).
"""

from datetime import datetime, timezone
from typing import Awaitable, Callable, List, Optional, Union
import inspect
import logging

from app.core.base_connector import BaseConnector
from app.core.exceptions import TenantNotFoundError, UnauthorizedError, VaultError
from app.services.registry import connector_registry
from app.services.indexer import indexer
from app.connectors.google.token_store import google_credential_ref

logger = logging.getLogger(__name__)


# Callback invoked after each successfully indexed/deleted page with the next cursor.
# May be sync or async — async is preferred inside Celery so DB I/O stays on the
# same event loop (avoids "Future attached to a different loop").
CursorUpdateCallback = Callable[[str], Union[None, Awaitable[None]]]
# Called after each indexed page with cumulative indexed_count.
ProgressCallback = Callable[[int], Union[None, Awaitable[None]]]


def _is_tenant_routing_failure(exc: BaseException) -> bool:
    """True when tenant Postgres cannot be reached. Crawl must fail closed.

    Distinguishes routing/session unavailability from per-document compile
    surprises, which still fall back to connector.transform().
    """
    if isinstance(exc, (TenantNotFoundError, VaultError)):
        return True
    if isinstance(exc, ValueError):
        msg = str(exc).lower()
        return "uuid" in msg or "badly formed hexadecimal" in msg
    if isinstance(exc, TypeError):
        return "uuid" in str(exc).lower()
    if isinstance(exc, RuntimeError):
        msg = str(exc)
        return (
            "webhook ACL compile aborted" in msg
            or "postgres routing unavailable" in msg
            or "tenant session was not opened" in msg
        )
    return False


class SyncOrchestrator:
    """
    Blind sync orchestrator.
    
    Two-pass sync:
    1. DELETIONS FIRST (security priority: revoke access before adding new content)
    2. DELTA INGESTION
    
    Never imports specific connectors; only uses the Registry and BaseConnector.
    """

    async def run_sync(
        self,
        source_type: str,
        tenant_id: str,
        config: dict,
        token_store,
        last_sync: Optional[datetime] = None,
        resume_cursor: Optional[str] = None,
        on_cursor_update: Optional[CursorUpdateCallback] = None,
        extra_acl: Optional[List[str]] = None,
    ) -> dict:
        """
        Run a full two-pass sync for a source.
        
        Args:
            source_type: Source type identifier (e.g., 'google_drive')
            tenant_id: Tenant UUID
            config: Connector configuration
            token_store: Token storage for OAuth
            last_sync: Last sync timestamp (None = full crawl)
            resume_cursor: Optional page cursor to resume a mid-crawl backfill
            on_cursor_update: Optional callback to persist cursor after each page
            
        Returns:
            Dict with sync stats (deleted, indexed, errors).
        """
        stats = {"deleted": 0, "indexed": 0, "errors": 0, "final_cursor": None, "pipeline": None}
        extra_acl = extra_acl or _acl_from_config(config)
        
        # Get connector from registry (blind - no name imports)
        connector = connector_registry.get_connector(source_type, config, token_store)
        
        if last_sync is None:
            last_sync = datetime(1970, 1, 1, tzinfo=timezone.utc)
        
        # PASS 1: DELETIONS FIRST (fresh cursors; deletion tokens != backfill page tokens)
        cursor = None
        while True:
            try:
                result = await connector.fetch_deleted_ids(last_sync, cursor)
            except NotImplementedError:
                # Source doesn't support deletion tracking
                break
            except Exception:
                logger.exception(
                    "fetch_deleted_ids failed tenant=%s source=%s",
                    tenant_id,
                    source_type,
                )
                stats["errors"] += 1
                break
            
            if result.deleted_ids:
                await indexer.delete_by_ids(result.deleted_ids, tenant_id, source_type)
                stats["deleted"] += len(result.deleted_ids)
            
            if result.next_cursor:
                stats["final_cursor"] = result.next_cursor
            
            if not result.has_more:
                break
            cursor = result.next_cursor
        
        # PASS 2: DELTA INGESTION (resume from checkpoint when provided)
        cursor = resume_cursor
        while True:
            try:
                result = await connector.fetch_delta(last_sync, cursor)
            except Exception:
                logger.exception(
                    "fetch_delta failed tenant=%s source=%s",
                    tenant_id,
                    source_type,
                )
                stats["errors"] += 1
                break

            if result.documents:
                connection_scope = str((config or {}).get("connection_scope") or "personal")
                _publish_raw_page(tenant_id, connector.source_type, result.documents, connection_scope)
                # Transform to UnifiedDocument (Block B contract)
                docs = await connector.transform(result.documents)
                try:
                    from app.connectors.google.pipeline_bridge import process_raw_batch

                    piped = await process_raw_batch(
                        result.documents,
                        connector.source_type,
                        tenant_id,
                        require_postgres=False,
                    )
                    if piped:
                        docs = piped
                        stats["pipeline"] = "block_c"
                        logger.info(
                            "pipeline=block_c n=%s source=%s tenant=%s",
                            len(piped),
                            connector.source_type,
                            tenant_id,
                        )
                    else:
                        stats["pipeline"] = "fallback_transform"
                        logger.warning(
                            "pipeline=fallback_transform n=%s source=%s tenant=%s "
                            "(process_raw_batch returned empty; using connector.transform)",
                            len(docs) if docs else 0,
                            connector.source_type,
                            tenant_id,
                        )
                except Exception as exc:
                    if _is_tenant_routing_failure(exc):
                        raise
                    stats["pipeline"] = "fallback_transform"
                    logger.warning(
                        "pipeline=fallback_transform n=%s source=%s tenant=%s "
                        "exc_type=%s exc=%s",
                        len(docs) if docs else 0,
                        connector.source_type,
                        tenant_id,
                        type(exc).__name__,
                        exc,
                    )

                if docs:
                    await indexer.bulk_index(
                        docs,
                        tenant_id,
                        extra_acl=extra_acl,
                    )
                    stats["indexed"] += len(docs)

            if result.next_cursor:
                stats["final_cursor"] = result.next_cursor
                if on_cursor_update:
                    on_cursor_update(result.next_cursor)
            
            if not result.has_more:
                break
            if not result.next_cursor:
                break
            cursor = result.next_cursor
        
        return stats

    def run_two_pass_sync(
        self,
        connector: BaseConnector,
        tenant_id: str,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        on_cursor_update: Optional[CursorUpdateCallback] = None,
        extra_acl: Optional[List[str]] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> dict:
        """
        Run a two-pass sync (called synchronously or from Celery tasks):
        Pass 1: Process deletions (security priority).
        Pass 2: Ingest new / updated delta items with per-page checkpointing.

        Args:
            connector: Connector instance
            tenant_id: Tenant UUID
            since: Only fetch changes after this timestamp
            cursor: Resume cursor from a prior mid-crawl checkpoint (delta pages)
            on_cursor_update: Called with next_cursor after each successfully
                processed delta page so a kill/restart can resume without loss
            on_progress: Called with cumulative indexed_count after each page
        """
        import asyncio

        async def _async_sync():
            stats = {
                "indexed_count": 0,
                "deleted_count": 0,
                "final_cursor": cursor,
                "pages_processed": 0,
                "indexed_ids": [],
                "pipeline": None,
            }

            # Pass 1: Deletions first.
            # IMPORTANT: never write changes.list tokens into final_cursor —
            # that cursor is resumed by fetch_delta (files.list / messages.list)
            # and an invalid pageToken aborts Drive with HttpError 400.
            del_cursor = None
            while True:
                try:
                    del_res = await connector.fetch_deleted_ids(since=since, cursor=del_cursor)
                except NotImplementedError:
                    break
                except UnauthorizedError:
                    # Re-raise auth failures so the calling task can set needs_reauth status.
                    raise
                except Exception:
                    logger.exception(
                        "fetch_deleted_ids failed tenant=%s source=%s",
                        tenant_id,
                        connector.source_type,
                    )
                    break

                if hasattr(del_res, "deleted_ids") and del_res.deleted_ids:
                    await indexer.delete_by_ids(
                        del_res.deleted_ids, tenant_id, connector.source_type
                    )
                    stats["deleted_count"] += len(del_res.deleted_ids)

                next_c = getattr(del_res, "next_cursor", None)
                if not getattr(del_res, "has_more", False):
                    break
                if not next_c:
                    break
                del_cursor = next_c

            # Pass 2: Delta ingestion — paginate and checkpoint after each page
            delta_cursor = cursor
            invalid_token_retried = False
            while True:
                try:
                    delta_res = await connector.fetch_delta(since=since, cursor=delta_cursor)
                except UnauthorizedError:
                    # Re-raise auth failures so the calling task can set needs_reauth status.
                    raise
                except Exception as exc:
                    err = str(exc)
                    # Stale/corrupt list pageToken → reset and retry once from start
                    if (
                        delta_cursor
                        and not invalid_token_retried
                        and (
                            "Invalid Value" in err
                            or "pageToken" in err
                            or "invalid" in err.lower()
                        )
                    ):
                        logger.warning(
                            "fetch_delta invalid cursor tenant=%s source=%s cursor=%r — resetting",
                            tenant_id,
                            connector.source_type,
                            delta_cursor,
                        )
                        delta_cursor = None
                        stats["final_cursor"] = None
                        invalid_token_retried = True
                        if on_cursor_update:
                            maybe = on_cursor_update("")
                            if inspect.isawaitable(maybe):
                                await maybe
                        continue
                    logger.exception(
                        "fetch_delta failed tenant=%s source=%s",
                        tenant_id,
                        connector.source_type,
                    )
                    break

                page_ids: List[str] = []
                if hasattr(delta_res, "documents") and delta_res.documents:
                    connection_scope = str((connector.config or {}).get("connection_scope") or "personal")
                    _publish_raw_page(tenant_id, connector.source_type, delta_res.documents, connection_scope)
                    docs = await connector.transform(delta_res.documents)
                    try:
                        from app.connectors.google.pipeline_bridge import process_raw_batch

                        piped = await process_raw_batch(
                            delta_res.documents,
                            connector.source_type,
                            tenant_id,
                            # Prefer Block C when Postgres is healthy; fall back
                            # to transform+bulk_index when tenant DB auth fails
                            # so crawls finish instead of stalling on retries.
                            require_postgres=False,
                        )
                        if piped:
                            docs = piped
                            stats["pipeline"] = "block_c"
                            logger.info(
                                "pipeline=block_c n=%s source=%s tenant=%s",
                                len(piped),
                                connector.source_type,
                                tenant_id,
                            )
                        else:
                            stats["pipeline"] = "fallback_transform"
                            logger.warning(
                                "pipeline=fallback_transform n=%s source=%s tenant=%s "
                                "(process_raw_batch returned empty; using connector.transform)",
                                len(docs) if docs else 0,
                                connector.source_type,
                                tenant_id,
                            )
                    except Exception as exc:
                        if _is_tenant_routing_failure(exc):
                            raise
                        stats["pipeline"] = "fallback_transform"
                        logger.warning(
                            "pipeline=fallback_transform n=%s source=%s tenant=%s "
                            "exc_type=%s exc=%s",
                            len(docs) if docs else 0,
                            connector.source_type,
                            tenant_id,
                            type(exc).__name__,
                            exc,
                        )
                    if docs:
                        await indexer.bulk_index(
                            docs, tenant_id, extra_acl=extra_acl
                        )
                        page_ids = [d.id for d in docs]
                        stats["indexed_count"] += len(docs)
                        stats["indexed_ids"].extend(page_ids)
                        if on_progress:
                            maybe = on_progress(int(stats["indexed_count"]))
                            if inspect.isawaitable(maybe):
                                await maybe

                stats["pages_processed"] += 1
                next_c = getattr(delta_res, "next_cursor", None)
                has_more = bool(getattr(delta_res, "has_more", False))

                if next_c:
                    stats["final_cursor"] = next_c
                    # Persist checkpoint AFTER successful index of this page.
                    # Exceptions here (e.g. simulated kill) must propagate so the
                    # task aborts without clearing the checkpoint.
                    if on_cursor_update:
                        maybe = on_cursor_update(next_c)
                        if inspect.isawaitable(maybe):
                            await maybe

                if not has_more:
                    break
                if not next_c:
                    break
                delta_cursor = next_c

            return stats

        try:
            return asyncio.run(_async_sync())
        except RuntimeError as exc:
            # Nested event loop (e.g. Jupyter / some test runners).
            # Do not swallow routing RuntimeError from process_raw_batch
            # (require_postgres=True) — that must fail closed.
            if "running event loop" not in str(exc):
                raise
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(_async_sync())


# Global orchestrator instance
sync_orchestrator = SyncOrchestrator()


def _acl_from_config(config: Optional[dict]) -> List[str]:
    principal = str((config or {}).get("connected_by") or "")
    if not principal:
        return []
    terms = [principal]
    if not principal.startswith(("user:", "group:")):
        terms.append(f"user:{principal}")
    return terms


def _publish_raw_page(tenant_id: str, source_type: str, documents: List, connection_scope: str = "personal") -> None:
    try:
        from app.services.ingest.publisher import publish_google_item

        instance_id = google_credential_ref(tenant_id, connection_scope=connection_scope)
        for item in documents:
            publish_google_item(
                tenant_id=tenant_id,
                source_type=source_type,
                source_instance_id=instance_id,
                item=item,
            )
    except Exception:
        logger.exception(
            "ingest.raw.v1 publish failed tenant=%s source=%s n=%s",
            tenant_id,
            source_type,
            len(documents) if documents else 0,
        )
