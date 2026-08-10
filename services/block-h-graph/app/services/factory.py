"""Factory for graph store backends."""

from app.config import settings
from app.services.graph_store import GraphStore
from app.services.mock_store import MockGraphStore

_mock_singleton: MockGraphStore | None = None
_neo4j_singleton = None


def get_graph_store(backend: str | None = None) -> GraphStore:
    """Return the configured GraphStore implementation."""
    global _mock_singleton, _neo4j_singleton
    kind = (backend or settings.graph_backend or "mock").lower()
    if kind == "neo4j":
        if _neo4j_singleton is None:
            from app.services.neo4j_store import Neo4jGraphStore

            _neo4j_singleton = Neo4jGraphStore()
        return _neo4j_singleton
    if _mock_singleton is None:
        _mock_singleton = MockGraphStore()
    return _mock_singleton


def reset_neo4j_store():
    global _neo4j_singleton
    _neo4j_singleton = None
    try:
        from app.services.neo4j_client import get_neo4j_manager
        get_neo4j_manager().close_all()
    except Exception:
        pass


def reset_mock_store() -> MockGraphStore:
    """Replace the mock singleton (test helper)."""
    global _mock_singleton
    _mock_singleton = MockGraphStore()
    return _mock_singleton
