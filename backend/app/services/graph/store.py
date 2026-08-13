"""Abstract graph store interface for Block H."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class GraphStore(ABC):
    """Tenant-isolated knowledge graph (one logical DB / namespace per tenant)."""

    @abstractmethod
    async def ensure_tenant(self, tenant_id: str) -> None:
        """Provision tenant graph namespace / Neo4j database."""

    @abstractmethod
    async def clear_tenant(self, tenant_id: str) -> None:
        """Remove all nodes/edges for a tenant (test helper)."""

    @abstractmethod
    async def upsert_node(
        self,
        tenant_id: str,
        label: str,
        source_id: str,
        properties: Dict[str, Any],
    ) -> None:
        """MERGE a node by (tenant_id, source_id) under the given label."""

    @abstractmethod
    async def upsert_edge(
        self,
        tenant_id: str,
        rel_type: str,
        source_id: str,
        target_id: str,
        properties: Optional[Dict[str, Any]] = None,
        source_label: Optional[str] = None,
        target_label: Optional[str] = None,
    ) -> None:
        """MERGE a relationship between two nodes (create stub nodes if needed)."""

    @abstractmethod
    async def delete_node(self, tenant_id: str, source_id: str) -> bool:
        """Delete a node and its relationships. Returns True if found."""

    @abstractmethod
    async def traverse(
        self,
        tenant_id: str,
        start_node_id: str,
        relationship_types: Optional[List[str]],
        depth: int,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Depth-limited relationship expansion.

        Returns {"nodes": [...], "relationships": [...]}
        """

    @abstractmethod
    async def people_search(
        self,
        tenant_id: str,
        query: str,
        department: Optional[str] = None,
        team: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search Person nodes by name/email/aliases with optional filters."""

    @abstractmethod
    async def related(
        self,
        tenant_id: str,
        node_id: str,
        depth: int = 1,
        limit: int = 50,
        relationship_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch nodes connected to the given node."""

    @abstractmethod
    async def count_edges_by_type(self, tenant_id: str) -> Dict[str, int]:
        """Return {rel_type: count} for edge-fidelity checks."""

    @abstractmethod
    async def get_edges_involving(
        self, tenant_id: str, source_id: str
    ) -> List[Dict[str, Any]]:
        """All edges where source_id is start or end."""

    @abstractmethod
    async def merge_persons(
        self, tenant_id: str, primary_id: str, secondary_id: str
    ) -> Dict[str, Any]:
        """
        Redirect all edges from secondary Person onto primary, then delete secondary.

        Returns {"edges_redirected": int, "secondary_deleted": bool, "snapshot": ...}
        """

    @abstractmethod
    async def split_persons(
        self,
        tenant_id: str,
        primary_id: str,
        secondary_id: str,
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Inverse of merge using a snapshot (restore secondary + edges)."""

    @abstractmethod
    async def list_node_ids(
        self, tenant_id: str, label: Optional[str] = None
    ) -> List[str]:
        """List source_ids for traversal latency sampling."""

    @abstractmethod
    async def health(self) -> Tuple[bool, str]:
        """Return (ok, detail) for readiness probes."""
