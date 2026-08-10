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
from typing import Callable, List, Optional

from app.core.base_connector import BaseConnector
from app.services.registry import connector_registry
from app.services.indexer import indexer


# Callback invoked after each successfully indexed/deleted page with the next cursor.
CursorUpdateCallback = Callable[[str], None]


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
        stats = {"deleted": 0, "indexed": 0, "errors": 0, "final_cursor": None}
        
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
                stats["errors"] += 1
                break
            
            if result.documents:
                # Transform to UnifiedDocument
                docs = await connector.transform(result.documents)
                
                if docs:
                    await indexer.bulk_index(docs, tenant_id)
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
        """
        import asyncio

        async def _async_sync():
            stats = {
                "indexed_count": 0,
                "deleted_count": 0,
                "final_cursor": cursor,
                "pages_processed": 0,
                "indexed_ids": [],
            }

            # Pass 1: Deletions first (do not reuse backfill page-token as deletion cursor)
            del_cursor = None
            while True:
                try:
                    del_res = await connector.fetch_deleted_ids(since=since, cursor=del_cursor)
                except NotImplementedError:
                    break
                except Exception:
                    break

                if hasattr(del_res, "deleted_ids") and del_res.deleted_ids:
                    await indexer.delete_by_ids(
                        del_res.deleted_ids, tenant_id, connector.source_type
                    )
                    stats["deleted_count"] += len(del_res.deleted_ids)

                next_c = getattr(del_res, "next_cursor", None)
                if next_c:
                    stats["final_cursor"] = next_c

                if not getattr(del_res, "has_more", False):
                    break
                if not next_c:
                    break
                del_cursor = next_c

            # Pass 2: Delta ingestion — paginate and checkpoint after each page
            delta_cursor = cursor
            while True:
                try:
                    delta_res = await connector.fetch_delta(since=since, cursor=delta_cursor)
                except Exception:
                    break

                page_ids: List[str] = []
                if hasattr(delta_res, "documents") and delta_res.documents:
                    docs = await connector.transform(delta_res.documents)
                    if docs:
                        await indexer.bulk_index(docs, tenant_id)
                        page_ids = [d.id for d in docs]
                        stats["indexed_count"] += len(docs)
                        stats["indexed_ids"].extend(page_ids)

                stats["pages_processed"] += 1
                next_c = getattr(delta_res, "next_cursor", None)
                has_more = bool(getattr(delta_res, "has_more", False))

                if next_c:
                    stats["final_cursor"] = next_c
                    # Persist checkpoint AFTER successful index of this page.
                    # Exceptions here (e.g. simulated kill) must propagate so the
                    # task aborts without clearing the checkpoint.
                    if on_cursor_update:
                        on_cursor_update(next_c)

                if not has_more:
                    break
                if not next_c:
                    break
                delta_cursor = next_c

            return stats

        try:
            return asyncio.run(_async_sync())
        except RuntimeError:
            # Nested event loop (e.g. Jupyter / some test runners)
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(_async_sync())


# Global orchestrator instance
sync_orchestrator = SyncOrchestrator()
