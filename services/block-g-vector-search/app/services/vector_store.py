"""Abstract vector store interface for Block G."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class VectorStore(ABC):
    """Tenant-isolated ANN store with ACL prefiltering."""

    @abstractmethod
    async def upsert_chunk(
        self,
        tenant_id: str,
        chunk_id: str,
        embedding: List[float],
        metadata: Dict[str, Any],
        acl_terms: List[str],
        model_version: str,
    ) -> None:
        """Insert or update a chunk embedding for a tenant."""

    @abstractmethod
    async def search(
        self,
        tenant_id: str,
        query_embedding: List[float],
        acl_terms: List[str],
        top_k: int = 100,
        model_version: Optional[str] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        ANN search with tenant + ACL prefilter.

        Returns dicts with keys:
          chunk_id, document_id, score, model_version, chunk_text, metadata
        """

    @abstractmethod
    async def delete_chunk(
        self,
        tenant_id: str,
        chunk_id: str,
        model_version: Optional[str] = None,
    ) -> None:
        """Delete a chunk (optionally scoped to one model version)."""

    @abstractmethod
    async def ensure_tenant(self, tenant_id: str, dimensions: int) -> None:
        """Ensure tenant collection / index exists."""

    @abstractmethod
    async def clear_tenant(self, tenant_id: str) -> None:
        """Remove all vectors for a tenant (test helper)."""
