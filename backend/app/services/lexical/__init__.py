"""
Lexical search services module.
Provides OpenSearch-backed full-text search with ACL filtering.
"""

from app.core.config import settings
from app.services.lexical.store import LexicalStore
from app.services.lexical.opensearch_store import OpenSearchLexicalStore


def get_lexical_store() -> LexicalStore:
    """Factory function to get lexical store based on configuration."""
    if settings.lexical_backend == "opensearch":
        return OpenSearchLexicalStore()
    else:  # "mock" or default
        from app.services.lexical.mock_store import MockLexicalStore
        return MockLexicalStore()


__all__ = ["LexicalStore", "OpenSearchLexicalStore", "get_lexical_store"]
