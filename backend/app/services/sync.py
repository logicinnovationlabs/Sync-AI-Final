"""
Blind Orchestrator: two-pass sync (deletion first, then delta).

This module orchestrates connector syncs WITHOUT ever importing specific connectors.
It only knows about BaseConnector and the Registry. Adding connector #11 requires
zero edits to this file.

Critical for the "Blind Orchestrator Rule."
"""

from datetime import datetime, timezone
from typing import Optional

from app.core.base_connector import BaseConnector
from app.services.registry import connector_registry
from app.services.indexer import indexer


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
    ) -> dict:
        """
        Run a full two-pass sync for a source.
        
        Args:
            source_type: Source type identifier (e.g., 'google_drive')
            tenant_id: Tenant UUID
            config: Connector configuration
            token_store: Token storage for OAuth
            last_sync: Last sync timestamp (None = full crawl)
            
        Returns:
            Dict with sync stats (deleted, indexed, errors).
        """
        stats = {"deleted": 0, "indexed": 0, "errors": 0}
        
        # Get connector from registry (blind - no name imports)
        connector = connector_registry.get_connector(source_type, config, token_store)
        
        if last_sync is None:
            last_sync = datetime(1970, 1, 1, tzinfo=timezone.utc)
        
        # PASS 1: DELETIONS FIRST
        cursor = None
        while True:
            try:
                result = await connector.fetch_deleted_ids(last_sync, cursor)
            except NotImplementedError:
                # Source doesn't support deletion tracking
                break
            except Exception as e:
                stats["errors"] += 1
                break
            
            if result.deleted_ids:
                await indexer.delete_by_ids(result.deleted_ids, tenant_id, source_type)
                stats["deleted"] += len(result.deleted_ids)
            
            if not result.has_more:
                break
            cursor = result.next_cursor
        
        # PASS 2: DELTA INGESTION
        cursor = None
        while True:
            try:
                result = await connector.fetch_delta(last_sync, cursor)
            except Exception as e:
                stats["errors"] += 1
                break
            
            if result.documents:
                # Transform to UnifiedDocument
                docs = await connector.transform(result.documents)
                
                if docs:
                    await indexer.bulk_index(docs, tenant_id)
                    stats["indexed"] += len(docs)
            
            if not result.has_more:
                break
            cursor = result.next_cursor
        
        return stats

    def run_two_pass_sync(
        self,
        connector: BaseConnector,
        tenant_id: str,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
    ) -> dict:
        """
        Run a two-pass sync (called synchronously or from Celery tasks):
        Pass 1: Process deletions (security priority).
        Pass 2: Ingest new / updated delta items.
        """
        import asyncio

        async def _async_sync():
            stats = {"indexed_count": 0, "deleted_count": 0, "final_cursor": None}

            # Pass 1: Deletions first
            try:
                del_res = await connector.fetch_deleted_ids(since=since, cursor=cursor)
                if hasattr(del_res, "deleted_ids") and del_res.deleted_ids:
                    await indexer.delete_by_ids(del_res.deleted_ids, tenant_id, connector.source_type)
                    stats["deleted_count"] = len(del_res.deleted_ids)
                if hasattr(del_res, "next_cursor") and del_res.next_cursor:
                    stats["final_cursor"] = del_res.next_cursor
            except Exception:
                pass

            # Pass 2: Delta Ingestion
            try:
                delta_res = await connector.fetch_delta(since=since, cursor=cursor)
                if hasattr(delta_res, "documents") and delta_res.documents:
                    docs = await connector.transform(delta_res.documents)
                    if docs:
                        await indexer.bulk_index(docs, tenant_id)
                        stats["indexed_count"] = len(docs)
                if hasattr(delta_res, "next_cursor") and delta_res.next_cursor:
                    stats["final_cursor"] = delta_res.next_cursor
            except Exception:
                pass

            return stats

        try:
            return asyncio.run(_async_sync())
        except Exception:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(_async_sync())


# Global orchestrator instance
sync_orchestrator = SyncOrchestrator()

