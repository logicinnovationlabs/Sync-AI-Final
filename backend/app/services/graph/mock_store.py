"""Mock in-memory graph store for testing without Neo4j."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
from app.services.graph.store import GraphStore


class MockGraphStore(GraphStore):
    """Full in-memory implementation of GraphStore for test environments."""

    def __init__(self):
        self.nodes: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.edges: Dict[str, List[Dict[str, Any]]] = {}
        self._snapshots: Dict[str, Dict[str, Any]] = {}

    async def ensure_tenant(self, tenant_id: str) -> None:
        if tenant_id not in self.nodes:
            self.nodes[tenant_id] = {}
        if tenant_id not in self.edges:
            self.edges[tenant_id] = []

    async def clear_tenant(self, tenant_id: str) -> None:
        self.nodes[tenant_id] = {}
        self.edges[tenant_id] = []

    async def upsert_node(
        self,
        tenant_id: str,
        label: str,
        source_id: str,
        properties: Dict[str, Any],
    ) -> None:
        await self.ensure_tenant(tenant_id)
        props = dict(properties or {})
        props["source_id"] = source_id
        props["label"] = label
        self.nodes[tenant_id][source_id] = {
            "label": label,
            "labels": [label],
            "source_id": source_id,
            "properties": props,
        }

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
        await self.ensure_tenant(tenant_id)
        # Ensure endpoint stub nodes exist if not present
        if source_id not in self.nodes[tenant_id]:
            self.nodes[tenant_id][source_id] = {
                "label": source_label or "Entity",
                "labels": [source_label or "Entity"],
                "source_id": source_id,
                "properties": {"source_id": source_id},
            }
        if target_id not in self.nodes[tenant_id]:
            self.nodes[tenant_id][target_id] = {
                "label": target_label or "Entity",
                "labels": [target_label or "Entity"],
                "source_id": target_id,
                "properties": {"source_id": target_id},
            }

        rel_type_normalized = rel_type.upper()
        # Look for existing edge to update
        for edge in self.edges[tenant_id]:
            if (
                edge["rel_type"] == rel_type_normalized
                and edge["source_id"] == source_id
                and edge["target_id"] == target_id
            ):
                edge["properties"].update(properties or {})
                return

        self.edges[tenant_id].append({
            "rel_type": rel_type_normalized,
            "source_id": source_id,
            "target_id": target_id,
            "properties": dict(properties or {}),
            "source_label": source_label,
            "target_label": target_label,
        })

    async def delete_node(self, tenant_id: str, source_id: str) -> bool:
        await self.ensure_tenant(tenant_id)
        if source_id in self.nodes[tenant_id]:
            del self.nodes[tenant_id][source_id]
            self.edges[tenant_id] = [
                e for e in self.edges[tenant_id]
                if e["source_id"] != source_id and e["target_id"] != source_id
            ]
            return True
        return False

    async def traverse(
        self,
        tenant_id: str,
        start_node_id: str,
        relationship_types: Optional[List[str]] = None,
        depth: int = 2,
        limit: int = 100,
    ) -> Dict[str, Any]:
        await self.ensure_tenant(tenant_id)
        if start_node_id not in self.nodes[tenant_id]:
            return {"nodes": [], "relationships": []}

        allowed_types = {t.upper() for t in relationship_types} if relationship_types else None
        visited_nodes: Set[str] = {start_node_id}
        collected_edges: List[Dict[str, Any]] = []
        current_layer: Set[str] = {start_node_id}

        for _ in range(depth):
            next_layer: Set[str] = set()
            for edge in self.edges[tenant_id]:
                if allowed_types and edge["rel_type"] not in allowed_types:
                    continue

                if edge["source_id"] in current_layer:
                    tgt = edge["target_id"]
                    collected_edges.append(edge)
                    if tgt not in visited_nodes:
                        visited_nodes.add(tgt)
                        next_layer.add(tgt)
                elif edge["target_id"] in current_layer:
                    src = edge["source_id"]
                    collected_edges.append(edge)
                    if src not in visited_nodes:
                        visited_nodes.add(src)
                        next_layer.add(src)

            current_layer = next_layer
            if not current_layer:
                break

        nodes_out = [
            self.nodes[tenant_id][nid]
            for nid in visited_nodes
            if nid in self.nodes[tenant_id]
        ]
        return {
            "nodes": nodes_out[:limit],
            "relationships": collected_edges[:limit],
        }

    async def people_search(
        self,
        tenant_id: str,
        query: str,
        department: Optional[str] = None,
        team: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        await self.ensure_tenant(tenant_id)
        results = []
        q = query.lower()
        for node in self.nodes[tenant_id].values():
            if node["label"] != "Person":
                continue
            props = node.get("properties", {})
            name = str(props.get("display_name", "")).lower()
            email = str(props.get("email", "")).lower()
            dept = str(props.get("department", "")).lower()
            tm = str(props.get("team", "")).lower()

            if department and dept != department.lower():
                continue
            if team and tm != team.lower():
                continue
            if q in name or q in email:
                results.append(node)
                if len(results) >= limit:
                    break
        return results

    async def related(
        self,
        tenant_id: str,
        node_id: str,
        depth: int = 1,
        limit: int = 50,
        relationship_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        traversal = await self.traverse(
            tenant_id, node_id, relationship_types=relationship_types, depth=depth, limit=limit
        )
        return [n for n in traversal["nodes"] if n["source_id"] != node_id]

    async def count_edges_by_type(self, tenant_id: str) -> Dict[str, int]:
        await self.ensure_tenant(tenant_id)
        counts: Dict[str, int] = {}
        for edge in self.edges[tenant_id]:
            rel_type = edge["rel_type"]
            counts[rel_type] = counts.get(rel_type, 0) + 1
        return counts

    async def get_edges_involving(
        self, tenant_id: str, source_id: str
    ) -> List[Dict[str, Any]]:
        await self.ensure_tenant(tenant_id)
        return [
            e for e in self.edges[tenant_id]
            if e["source_id"] == source_id or e["target_id"] == source_id
        ]

    async def merge_persons(
        self, tenant_id: str, primary_id: str, secondary_id: str
    ) -> Dict[str, Any]:
        await self.ensure_tenant(tenant_id)
        involving = await self.get_edges_involving(tenant_id, secondary_id)
        secondary_node = self.nodes[tenant_id].get(secondary_id)

        snapshot = {
            "secondary_id": secondary_id,
            "secondary_node": secondary_node,
            "original_edges": [dict(e) for e in involving],
        }

        redirected = 0
        for edge in self.edges[tenant_id]:
            if edge["source_id"] == secondary_id:
                edge["source_id"] = primary_id
                redirected += 1
            if edge["target_id"] == secondary_id:
                edge["target_id"] = primary_id
                redirected += 1

        if secondary_id in self.nodes[tenant_id]:
            del self.nodes[tenant_id][secondary_id]

        return {
            "edges_redirected": redirected,
            "secondary_deleted": True,
            "snapshot": snapshot,
        }

    async def split_persons(
        self,
        tenant_id: str,
        primary_id: str,
        secondary_id: str,
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.ensure_tenant(tenant_id)
        if not snapshot:
            return {"restored": False, "edges_restored": 0}

        # Restore node
        if snapshot.get("secondary_node"):
            self.nodes[tenant_id][secondary_id] = snapshot["secondary_node"]

        # Restore edges from snapshot
        orig_edges = snapshot.get("original_edges", [])
        # Remove redirected edges from primary that belong to secondary snapshot
        for orig in orig_edges:
            rel_type = orig["rel_type"]
            s = primary_id if orig["source_id"] == secondary_id else orig["source_id"]
            t = primary_id if orig["target_id"] == secondary_id else orig["target_id"]
            for edge in list(self.edges[tenant_id]):
                if edge["rel_type"] == rel_type and edge["source_id"] == s and edge["target_id"] == t:
                    self.edges[tenant_id].remove(edge)
                    break
            self.edges[tenant_id].append(dict(orig))

        return {
            "restored": True,
            "edges_restored": len(orig_edges),
        }

    async def list_node_ids(
        self, tenant_id: str, label: Optional[str] = None
    ) -> List[str]:
        await self.ensure_tenant(tenant_id)
        if label:
            return [
                nid for nid, data in self.nodes[tenant_id].items()
                if data.get("label") == label or label in data.get("labels", [])
            ]
        return list(self.nodes[tenant_id].keys())

    async def health(self) -> Tuple[bool, str]:
        return True, "MockGraphStore healthy"
