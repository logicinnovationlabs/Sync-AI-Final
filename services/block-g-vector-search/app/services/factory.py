"""Factory for vector store backends."""

from functools import lru_cache

from app.config import settings
from app.services.mock_store import MockVectorStore
from app.services.qdrant_store import QdrantVectorStore
from app.services.vector_store import VectorStore

# Process-wide mock instance so API + tests share state in Phase 1
_mock_singleton: MockVectorStore | None = None


def get_vector_store(db_type: str | None = None) -> VectorStore:
    """Return the configured VectorStore implementation."""
    global _mock_singleton
    kind = (db_type or settings.vector_db_type or "mock").lower()
    if kind == "qdrant":
        return QdrantVectorStore()
    if _mock_singleton is None:
        _mock_singleton = MockVectorStore()
    return _mock_singleton


def reset_mock_store() -> MockVectorStore:
    """Replace the mock singleton (test helper)."""
    global _mock_singleton
    _mock_singleton = MockVectorStore()
    return _mock_singleton


@lru_cache
def cached_settings_db_type() -> str:
    return settings.vector_db_type.lower()
