"""
Vector search store interface and base class.
Abstract interface for Qdrant and mock implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class VectorStore(ABC):
    """Abstract base class for vector search stores."""
    
    @abstractmethod
    async def search(
        self,
        tenant_id: str,
        query_embedding: List[float],
        acl_terms: List[str],
        top_k: int = 10,
        model_version: Optional[str] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute semantic vector search with ACL filtering.
        
        Args:
            tenant_id: Tenant identifier
            query_embedding: Query vector embedding
            acl_terms: ACL filter terms (fail-closed if empty)
            top_k: Number of results to return
            model_version: Filter by embedding model version
            score_threshold: Minimum similarity score
            
        Returns:
            List of dicts with keys: chunk_id, document_id, score, model_version, chunk_text, metadata
        """
        pass
    
    @abstractmethod
    async def upsert_chunk(
        self,
        tenant_id: str,
        chunk_id: str,
        document_id: str,
        embedding: List[float],
        model_version: str,
        acl_terms: List[str],
        chunk_text: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Upsert a single chunk vector."""
        pass
    
    @abstractmethod
    async def upsert_batch(
        self,
        tenant_id: str,
        chunks: List[Dict[str, Any]],
    ) -> int:
        """Bulk upsert chunk vectors. Returns count."""
        pass
    
    @abstractmethod
    async def delete_chunk(
        self,
        tenant_id: str,
        chunk_id: str,
        model_version: str,
    ) -> None:
        """Delete a chunk vector."""
        pass
