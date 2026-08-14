"""
Lexical search services module.
Provides OpenSearch-backed full-text search with ACL filtering.
"""

from app.core.config import settings
from app.services.lexical.store import LexicalStore
from app.services.lexical.opensearch_store import OpenSearchLexicalStore


def get_lexical_store() -> LexicalStore:
    """Factory function to get lexical store - always returns real OpenSearch for tests."""
    # For signoff tests, always use real OpenSearch
    return OpenSearchLexicalStore()


__all__ = ["LexicalStore", "OpenSearchLexicalStore", "get_lexical_store"]
