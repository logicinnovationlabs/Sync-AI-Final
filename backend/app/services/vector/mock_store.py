"""Mock vector store for testing without Qdrant."""

from typing import List, Dict, Any, Optional

from app.acl.filter import document_is_visible, is_fail_closed
from app.services.vector.store import VectorStore


class MockVectorStore(VectorStore):
    """Mock implementation of VectorStore for testing."""

    def __init__(self):
        self.chunks = {}

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
        if tenant_id not in self.chunks:
            self.chunks[tenant_id] = {}
        self.chunks[tenant_id][chunk_id] = {
            "embedding": embedding,
            "document_id": document_id,
            "model_version": model_version,
            "acl_terms": list(acl_terms or []),
            "chunk_text": chunk_text,
            "metadata": metadata or {},
        }

    async def upsert_batch(self, tenant_id: str, chunks: List[Dict[str, Any]]) -> int:
        for chunk in chunks:
            await self.upsert_chunk(
                tenant_id=tenant_id,
                chunk_id=chunk["chunk_id"],
                document_id=chunk.get("document_id", chunk["chunk_id"]),
                embedding=chunk["embedding"],
                model_version=chunk.get("model_version", "v1"),
                acl_terms=chunk.get("acl_terms") or chunk.get("acl_filter_terms") or [],
                chunk_text=chunk.get("chunk_text", ""),
                metadata=chunk.get("metadata"),
            )
        return len(chunks)

    async def search(
        self,
        tenant_id: str,
        query_embedding: List[float],
        acl_terms: List[str],
        top_k: int = 10,
        model_version: Optional[str] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        if is_fail_closed(acl_terms):
            return []
        if tenant_id not in self.chunks:
            return []

        results = []
        for chunk_id, chunk_data in self.chunks[tenant_id].items():
            if model_version and chunk_data.get("model_version") != model_version:
                continue
            if not document_is_visible(acl_terms, chunk_data.get("acl_terms") or []):
                continue
            results.append({
                "chunk_id": chunk_id,
                "document_id": chunk_data.get("document_id", chunk_id),
                "score": 1.0,
                "model_version": chunk_data.get("model_version", ""),
                "chunk_text": chunk_data.get("chunk_text", ""),
                "metadata": chunk_data.get("metadata"),
            })
            if len(results) >= top_k:
                break
        return results

    async def delete_chunk(
        self,
        tenant_id: str,
        chunk_id: str,
        model_version: str = "",
    ) -> None:
        if tenant_id in self.chunks and chunk_id in self.chunks[tenant_id]:
            del self.chunks[tenant_id][chunk_id]

    async def clear_tenant(self, tenant_id: str):
        if tenant_id in self.chunks:
            del self.chunks[tenant_id]
