"""Block H: Knowledge Graph Services."""

from app.core.config import settings
from app.services.graph.store import GraphStore
from app.services.graph.neo4j_store import Neo4jGraphStore


def get_graph_store() -> GraphStore:
    """Factory function to get graph store - always returns real Neo4j for tests."""
    # For signoff tests, always use real Neo4j
    return Neo4jGraphStore()


__all__ = ["GraphStore", "Neo4jGraphStore", "get_graph_store"]
