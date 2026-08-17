"""Block H: Knowledge Graph Services."""

import os
from app.core.config import settings
from app.services.graph.store import GraphStore
from app.services.graph.neo4j_store import Neo4jGraphStore
from app.services.graph.mock_store import MockGraphStore

_mock_instance = None


def get_graph_store() -> GraphStore:
    """Factory function to get graph store (Neo4j or in-memory Mock)."""
    global _mock_instance
    backend = os.getenv("GRAPH_BACKEND", "").lower()
    if backend == "mock":
        if _mock_instance is None:
            _mock_instance = MockGraphStore()
        return _mock_instance
    try:
        return Neo4jGraphStore()
    except Exception:
        if _mock_instance is None:
            _mock_instance = MockGraphStore()
        return _mock_instance


__all__ = ["GraphStore", "Neo4jGraphStore", "MockGraphStore", "get_graph_store"]
