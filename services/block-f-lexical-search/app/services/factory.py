"""Factory for lexical store backends."""

from app.config import settings
from app.services.lexical_store import LexicalStore
from app.services.mock_store import MockLexicalStore

_mock_singleton: MockLexicalStore | None = None


def get_lexical_store(backend: str | None = None) -> LexicalStore:
    """Return the configured LexicalStore implementation."""
    global _mock_singleton
    kind = (backend or settings.search_backend or "mock").lower()
    if kind in ("opensearch", "elasticsearch", "es", "os"):
        from app.services.opensearch_store import OpenSearchLexicalStore

        return OpenSearchLexicalStore()
    if _mock_singleton is None:
        _mock_singleton = MockLexicalStore()
    return _mock_singleton


def reset_mock_store() -> MockLexicalStore:
    """Replace the mock singleton (test helper)."""
    global _mock_singleton
    _mock_singleton = MockLexicalStore()
    return _mock_singleton
