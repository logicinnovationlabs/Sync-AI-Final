"""Mock graph store for testing without Neo4j."""

from typing import List, Dict, Any, Optional
from app.services.graph.store import GraphStore


class MockGraphStore(GraphStore):
    """Mock implementation of GraphStore for testing."""
    
    def __init__(self):
        self.nodes = {}
        self.edges = {}
    
    async def ensure_tenant(self, tenant_id: str):
        """Mock ensure tenant."""
        if tenant_id not in self.nodes:
            self.nodes[tenant_id] = {}
            self.edges[tenant_id] = []
    
    async def upsert_node(self, tenant_id: str, label: str, node_id: str, properties: Dict[str, Any]):
        """Mock upsert node."""
        if tenant_id not in self.nodes:
            self.nodes[tenant_id] = {}
        self.nodes[tenant_id][node_id] = {
            "label": label,
            "properties": properties
        }
    
    async def upsert_edge(self, tenant_id: str, rel_type: str, source_id: str, target_id: str,
                         properties: Dict[str, Any] = None, source_label: str = None, target_label: str = None):
        """Mock upsert edge."""
        if tenant_id not in self.edges:
            self.edges[tenant_id] = []
        self.edges[tenant_id].append({
            "rel_type": rel_type,
            "source_id": source_id,
            "target_id": target_id,
            "properties": properties or {},
            "source_label": source_label,
            "target_label": target_label
        })
    
    async def traverse(self, tenant_id: str, start_node_id: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """Mock traverse."""
        return []
    
    async def list_node_ids(self, tenant_id: str) -> List[str]:
        """Mock list node IDs."""
        if tenant_id not in self.nodes:
            return []
        return list(self.nodes[tenant_id].keys())
    
    async def get_edge_counts_by_type(self, tenant_id: str) -> Dict[str, int]:
        """Mock get edge counts by type."""
        if tenant_id not in self.edges:
            return {}
        counts = {}
        for edge in self.edges[tenant_id]:
            rel_type = edge["rel_type"]
            counts[rel_type] = counts.get(rel_type, 0) + 1
        return counts
    
    async def clear_tenant(self, tenant_id: str):
        """Mock clear tenant."""
        if tenant_id in self.nodes:
            del self.nodes[tenant_id]
        if tenant_id in self.edges:
            del self.edges[tenant_id]
