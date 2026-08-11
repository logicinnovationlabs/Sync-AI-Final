"""
Lexical search services module.
Provides OpenSearch-backed full-text search with ACL filtering.
"""

from app.services.lexical.store import LexicalStore
from app.services.lexical.opensearch_store import OpenSearchLexicalStore

__all__ = ["LexicalStore", "OpenSearchLexicalStore"]
