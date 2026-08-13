"""
Vector search services module.
Provides Qdrant-backed semantic search with ACL filtering.
"""

from app.core.config import settings
from app.services.vector.store import VectorStore
from app.services.vector.qdrant_store import QdrantVectorStore


def get_vector_store() -> VectorStore:
    """Factory function to get vector store based on configuration."""
    if settings.vector_backend == "qdrant":
        return QdrantVectorStore()
    else:  # "mock" or default
        from app.services.vector.mock_store import MockVectorStore
        return MockVectorStore()


__all__ = ["VectorStore", "QdrantVectorStore", "get_vector_store"]
