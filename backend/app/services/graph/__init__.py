"""Block H: Knowledge Graph Services."""

from app.core.config import settings
from app.services.graph.store import GraphStore
from app.services.graph.neo4j_store import Neo4jGraphStore


def get_graph_store() -> GraphStore:
    """Factory function to get graph store based on configuration."""
    if settings.graph_backend == "neo4j":
        return Neo4jGraphStore()
    else:  # "mock" or default
        from app.services.graph.mock_store import MockGraphStore
        return MockGraphStore()


__all__ = ["GraphStore", "Neo4jGraphStore", "get_graph_store"]
