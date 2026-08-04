"""
Component 7: Orphan and Tombstone Handling
Handles orphan chunks and tombstones when documents are re-chunked.
"""

from typing import List, Dict, Any
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.chunk_record import ChunkRecord


class OrphanHandler:
    """
    Handles orphan chunks and tombstones when documents are re-chunked.
    
    Per §10.7: When a document is re-chunked, old chunks become orphans.
    Orphans should be marked as tombstones (deleted_at set) rather than
    hard-deleted, to maintain audit trail and enable recovery.
    """
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
    
    def get_current_chunks(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int
    ) -> List[ChunkRecord]:
        """
        Get current chunks for a document version.
        
        Args:
            tenant_id: Tenant identifier
            document_id: Document identifier
            document_version: Document version
        
        Returns:
            List of current chunks
        """
        result = self.db_session.execute(
            select(ChunkRecord).where(
                ChunkRecord.tenant_id == tenant_id,
                ChunkRecord.document_id == document_id,
                ChunkRecord.document_version == document_version,
                ChunkRecord.deleted_at.is_(None)
            )
        )
        return result.scalars().all()
    
    def get_previous_chunks(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int
    ) -> List[ChunkRecord]:
        """
        Get previous chunks for a document (older versions).
        
        Args:
            tenant_id: Tenant identifier
            document_id: Document identifier
            document_version: Current document version (exclude this)
        
        Returns:
            List of previous chunks (not tombstoned)
        """
        result = self.db_session.execute(
            select(ChunkRecord).where(
                ChunkRecord.tenant_id == tenant_id,
                ChunkRecord.document_id == document_id,
                ChunkRecord.document_version < document_version,
                ChunkRecord.deleted_at.is_(None)
            )
        )
        return result.scalars().all()
    
    def mark_as_tombstone(
        self,
        chunk_id: str
    ) -> bool:
        """
        Mark a chunk as tombstone (soft delete).
        
        Args:
            chunk_id: Chunk identifier
        
        Returns:
            True if marked, False if not found
        """
        result = self.db_session.execute(
            update(ChunkRecord)
            .where(ChunkRecord.chunk_id == chunk_id)
            .values(deleted_at=datetime.utcnow())
        )
        
        self.db_session.commit()
        
        marked = result.rowcount > 0
        if marked:
            print(f"[ORPHAN] Marked chunk {chunk_id} as tombstone")
        
        return marked
    
    def mark_previous_as_tombstones(
        self,
        tenant_id: str,
        document_id: str,
        current_document_version: int
    ) -> int:
        """
        Mark all previous chunks for a document as tombstones.
        
        This is called after re-chunking to clean up old versions.
        
        Args:
            tenant_id: Tenant identifier
            document_id: Document identifier
            current_document_version: Current document version (mark older versions)
        
        Returns:
            Number of chunks marked as tombstones
        """
        result = self.db_session.execute(
            update(ChunkRecord)
            .where(
                ChunkRecord.tenant_id == tenant_id,
                ChunkRecord.document_id == document_id,
                ChunkRecord.document_version < current_document_version,
                ChunkRecord.deleted_at.is_(None)
            )
            .values(deleted_at=datetime.utcnow())
        )
        
        self.db_session.commit()
        
        count = result.rowcount
        print(f"[ORPHAN] Marked {count} previous chunks as tombstones for document {document_id}")
        
        return count
    
    def get_orphan_chunks(
        self,
        tenant_id: str,
        document_id: str,
        current_chunk_ids: List[str]
    ) -> List[ChunkRecord]:
        """
        Get orphan chunks (chunks not in current chunk list).
        
        Args:
            tenant_id: Tenant identifier
            document_id: Document identifier
            current_chunk_ids: List of current chunk IDs
        
        Returns:
            List of orphan chunks
        """
        result = self.db_session.execute(
            select(ChunkRecord).where(
                ChunkRecord.tenant_id == tenant_id,
                ChunkRecord.document_id == document_id,
                ChunkRecord.chunk_id.notin_(current_chunk_ids),
                ChunkRecord.deleted_at.is_(None)
            )
        )
        return result.scalars().all()
    
    def handle_re_chunk(
        self,
        tenant_id: str,
        document_id: str,
        new_document_version: int,
        new_chunk_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Handle orphan chunks when a document is re-chunked.
        
        Args:
            tenant_id: Tenant identifier
            document_id: Document identifier
            new_document_version: New document version
            new_chunk_ids: List of new chunk IDs
        
        Returns:
            Dictionary with handling results
        """
        # Get orphan chunks (old chunks not in new chunk list)
        orphans = self.get_orphan_chunks(tenant_id, document_id, new_chunk_ids)
        
        orphan_ids = [chunk.chunk_id for chunk in orphans]
        
        # Mark orphans as tombstones
        marked_count = 0
        for chunk_id in orphan_ids:
            if self.mark_as_tombstone(chunk_id):
                marked_count += 1
        
        # Mark all previous version chunks as tombstones
        previous_marked = self.mark_previous_as_tombstones(
            tenant_id,
            document_id,
            new_document_version
        )
        
        return {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "new_document_version": new_document_version,
            "orphan_chunks_found": len(orphans),
            "orphan_chunk_ids": orphan_ids,
            "orphans_marked_as_tombstones": marked_count,
            "previous_versions_marked": previous_marked,
            "total_tombstoned": marked_count + previous_marked
        }
