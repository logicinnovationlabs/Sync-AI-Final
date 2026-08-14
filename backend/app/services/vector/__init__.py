"""
Vector search services module.
Provides Qdrant-backed semantic search with ACL filtering.
"""

from app.core.config import settings
from app.services.vector.store import VectorStore
from app.services.vector.qdrant_store import QdrantVectorStore


def get_vector_store() -> VectorStore:
    """Factory function to get vector store - always returns real Qdrant for tests."""
    # For signoff tests, always use real Qdrant
    return QdrantVectorStore()


__all__ = ["VectorStore", "QdrantVectorStore", "get_vector_store"]
