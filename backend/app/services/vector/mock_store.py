"""Mock vector store for testing without Qdrant."""

from typing import List, Dict, Any
from app.services.vector.store import VectorStore


class MockVectorStore(VectorStore):
    """Mock implementation of VectorStore for testing."""
    
    def __init__(self):
        self.chunks = {}
    
    async def upsert_chunk(self, tenant_id: str, chunk_id: str, embedding: List[float], metadata: Dict[str, Any] = None):
        """Mock upsert chunk."""
        if tenant_id not in self.chunks:
            self.chunks[tenant_id] = {}
        self.chunks[tenant_id][chunk_id] = {
            "embedding": embedding,
            "metadata": metadata or {}
        }
    
    async def search(self, tenant_id: str, query_embedding: List[float], acl_terms: List[str], 
                    top_k: int = 10, model_version: str = None) -> List[Dict[str, Any]]:
        """Mock search."""
        if tenant_id not in self.chunks:
            return []
        
        # Simple mock: return first top_k chunks
        results = []
        for chunk_id, chunk_data in list(self.chunks[tenant_id].items())[:top_k]:
            results.append({
                "chunk_id": chunk_id,
                "score": 1.0,
                **chunk_data["metadata"]
            })
        return results
    
    async def delete_chunk(self, tenant_id: str, chunk_id: str):
        """Mock delete chunk."""
        if tenant_id in self.chunks and chunk_id in self.chunks[tenant_id]:
            del self.chunks[tenant_id][chunk_id]
    
    async def clear_tenant(self, tenant_id: str):
        """Mock clear tenant."""
        if tenant_id in self.chunks:
            del self.chunks[tenant_id]
