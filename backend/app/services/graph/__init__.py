"""Block H: Knowledge Graph Services."""

from app.core.backends import mock_backends_allowed, refuse_mock_backend
from app.core.config import settings
from app.services.graph.store import GraphStore
from app.services.graph.neo4j_store import Neo4jGraphStore
from app.services.graph.mock_store import MockGraphStore

_mock_instance = None
_neo4j_instance = None


def get_graph_store() -> GraphStore:
    """Process-level graph store. Mock is a singleton so request-scoped factories share state."""
    global _mock_instance, _neo4j_instance
    backend = (settings.graph_backend or "mock").strip().lower()
    if backend == "neo4j":
        if _neo4j_instance is None:
            _neo4j_instance = Neo4jGraphStore()
        return _neo4j_instance
    refuse_mock_backend("GRAPH_BACKEND", backend, "neo4j")
    if not mock_backends_allowed():
        raise RuntimeError("GRAPH_BACKEND=mock is not allowed outside development/test")
    if _mock_instance is None:
        _mock_instance = MockGraphStore()
    return _mock_instance


__all__ = ["GraphStore", "Neo4jGraphStore", "MockGraphStore", "get_graph_store"]
