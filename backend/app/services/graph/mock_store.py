"""In-memory mock graph store for Phase 1 provisional signoff."""

from __future__ import annotations

import copy
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.graph.store import GraphStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MockGraphStore(GraphStore):
    """
    Per-tenant in-memory graph.

    Isolation: each tenant_id has a completely separate node/edge dict —
    mirrors Neo4j one-database-per-tenant without sharing storage.
    """

    def __init__(self) -> None:
        # tenant_id -> source_id -> node dict
        self._nodes: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        # tenant_id -> list of edge dicts
        self._edges: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        # merge snapshots for split restore
        self._merge_snapshots: Dict[str, Dict[str, Any]] = {}

    async def ensure_tenant(self, tenant_id: str) -> None:
        _ = self._nodes[tenant_id]
        _ = self._edges[tenant_id]

    async def clear_tenant(self, tenant_id: str) -> None:
        self._nodes.pop(tenant_id, None)
        self._edges.pop(tenant_id, None)
        # Drop snapshots for this tenant
        drop = [k for k in self._merge_snapshots if k.startswith(f"{tenant_id}:")]
        for k in drop:
            del self._merge_snapshots[k]

    async def upsert_node(
        self,
        tenant_id: str,
        label: str,
        source_id: str,
        properties: Dict[str, Any],
    ) -> None:
        await self.ensure_tenant(tenant_id)
        nodes = self._nodes[tenant_id]
        existing = nodes.get(source_id)
        incoming_updated = properties.get("updated_at")
        if existing and incoming_updated and existing.get("updated_at"):
            # Idempotency: skip stale updates
            if str(incoming_updated) < str(existing.get("updated_at")):
                return
        labels: Set[str] = set(existing["labels"]) if existing else set()
        labels.add(label)
        props = dict(existing.get("properties", {})) if existing else {}
        props.update({k: v for k, v in properties.items() if v is not None})
        props["tenant_id"] = tenant_id
        props["source_id"] = source_id
        props.setdefault("created_at", properties.get("created_at") or _now())
        props["updated_at"] = properties.get("updated_at") or _now()
        nodes[source_id] = {
            "source_id": source_id,
            "labels": sorted(labels),
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
        # Ensure stub nodes exist
        if source_id not in self._nodes[tenant_id]:
            await self.upsert_node(
                tenant_id,
                source_label or "Entity",
                source_id,
                {"tenant_id": tenant_id},
            )
        elif source_label and source_label not in self._nodes[tenant_id][source_id]["labels"]:
            await self.upsert_node(tenant_id, source_label, source_id, {})
        if target_id not in self._nodes[tenant_id]:
            await self.upsert_node(
                tenant_id,
                target_label or "Entity",
                target_id,
                {"tenant_id": tenant_id},
            )
        elif target_label and target_label not in self._nodes[tenant_id][target_id]["labels"]:
            await self.upsert_node(tenant_id, target_label, target_id, {})

        edges = self._edges[tenant_id]
        for e in edges:
            if (
                e["type"] == rel_type
                and e["source_id"] == source_id
                and e["target_id"] == target_id
            ):
                e["properties"] = {**(e.get("properties") or {}), **(properties or {})}
                return
        edges.append(
            {
                "type": rel_type,
                "source_id": source_id,
                "target_id": target_id,
                "properties": dict(properties or {}),
            }
        )

    async def delete_node(self, tenant_id: str, source_id: str) -> bool:
        nodes = self._nodes.get(tenant_id) or {}
        if source_id not in nodes:
            return False
        del nodes[source_id]
        self._edges[tenant_id] = [
            e
            for e in self._edges[tenant_id]
            if e["source_id"] != source_id and e["target_id"] != source_id
        ]
        return True

    def _adj(
        self, tenant_id: str, rel_types: Optional[Set[str]]
    ) -> Dict[str, List[Tuple[str, Dict[str, Any]]]]:
        adj: Dict[str, List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)
        for e in self._edges.get(tenant_id, []):
            if rel_types and e["type"] not in rel_types:
                continue
            adj[e["source_id"]].append((e["target_id"], e))
            # undirected expansion for traversal (as APOC expand does by default with '+')
            adj[e["target_id"]].append((e["source_id"], e))
        return adj

    async def traverse(
        self,
        tenant_id: str,
        start_node_id: str,
        relationship_types: Optional[List[str]],
        depth: int,
        limit: int = 100,
    ) -> Dict[str, Any]:
        nodes_map = self._nodes.get(tenant_id) or {}
        if start_node_id not in nodes_map:
            return {"nodes": [], "relationships": []}

        rel_filter = set(relationship_types) if relationship_types else None
        adj = self._adj(tenant_id, rel_filter)

        seen_nodes: Set[str] = {start_node_id}
        seen_edges: Set[Tuple[str, str, str]] = set()
        collected_edges: List[Dict[str, Any]] = []

        q: deque[Tuple[str, int]] = deque([(start_node_id, 0)])
        while q and len(collected_edges) < limit:
            current, d = q.popleft()
            if d >= depth:
                continue
            for neighbor, edge in adj.get(current, []):
                key = (edge["type"], edge["source_id"], edge["target_id"])
                if key not in seen_edges:
                    seen_edges.add(key)
                    collected_edges.append(edge)
                    if len(collected_edges) >= limit:
                        break
                if neighbor not in seen_nodes:
                    seen_nodes.add(neighbor)
                    q.append((neighbor, d + 1))

        out_nodes = []
        for nid in seen_nodes:
            n = nodes_map.get(nid)
            if n:
                out_nodes.append(
                    {
                        "source_id": n["source_id"],
                        "labels": list(n["labels"]),
                        "properties": dict(n["properties"]),
                    }
                )
        return {"nodes": out_nodes, "relationships": list(collected_edges)[:limit]}

    async def people_search(
        self,
        tenant_id: str,
        query: str,
        department: Optional[str] = None,
        team: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        q = (query or "").lower()
        results: List[Dict[str, Any]] = []
        for node in (self._nodes.get(tenant_id) or {}).values():
            if "Person" not in node["labels"]:
                continue
            props = node["properties"]
            if department and props.get("department") != department:
                continue
            if team and props.get("team") != team:
                continue
            name = str(props.get("display_name") or "").lower()
            email = str(props.get("email") or "").lower()
            aliases = [str(a).lower() for a in (props.get("aliases") or [])]
            if q and not (
                q in name or q in email or any(q in a for a in aliases)
            ):
                continue
            results.append(
                {
                    "id": node["source_id"],
                    "display_name": props.get("display_name"),
                    "email": props.get("email"),
                    "title": props.get("title"),
                    "department": props.get("department"),
                    "team": props.get("team"),
                    "aliases": list(props.get("aliases") or []),
                    "properties": dict(props),
                }
            )
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
        # depth>1: reuse traverse and flatten 1-hop style results from collected edges
        trav = await self.traverse(
            tenant_id, node_id, relationship_types, depth=max(depth, 1), limit=limit * 2
        )
        nodes_by_id = {n["source_id"]: n for n in trav["nodes"]}
        out: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for e in trav["relationships"]:
            other = e["target_id"] if e["source_id"] == node_id else (
                e["source_id"] if e["target_id"] == node_id else None
            )
            if other is None:
                # multi-hop: include either endpoint that isn't the start
                if e["source_id"] != node_id:
                    other = e["source_id"]
                elif e["target_id"] != node_id:
                    other = e["target_id"]
            if other is None or other == node_id or other in seen:
                continue
            if other not in nodes_by_id:
                continue
            seen.add(other)
            out.append(
                {
                    "related": nodes_by_id[other],
                    "rel_type": e["type"],
                    "direction": (
                        "out" if e["source_id"] == node_id else "in"
                    ),
                }
            )
            if len(out) >= limit:
                break
        return out

    async def count_edges_by_type(self, tenant_id: str) -> Dict[str, int]:
        counts: Dict[str, int] = defaultdict(int)
        for e in self._edges.get(tenant_id, []):
            counts[e["type"]] += 1
        return dict(counts)

    async def get_edges_involving(
        self, tenant_id: str, source_id: str
    ) -> List[Dict[str, Any]]:
        return [
            e
            for e in self._edges.get(tenant_id, [])
            if e["source_id"] == source_id or e["target_id"] == source_id
        ]

    async def merge_persons(
        self, tenant_id: str, primary_id: str, secondary_id: str
    ) -> Dict[str, Any]:
        nodes = self._nodes.get(tenant_id) or {}
        if primary_id not in nodes or secondary_id not in nodes:
            raise KeyError("primary or secondary Person not found")
        if "Person" not in nodes[primary_id]["labels"]:
            raise ValueError("primary_id is not a Person")
        if "Person" not in nodes[secondary_id]["labels"]:
            raise ValueError("secondary_id is not a Person")

        # Snapshot for optional split restore
        sec_node = copy.deepcopy(nodes[secondary_id])
        involving = copy.deepcopy(await self.get_edges_involving(tenant_id, secondary_id))

        # Existing edge keys before redirect (to distinguish new vs absorbed)
        existing_keys = {
            (e["type"], e["source_id"], e["target_id"]) for e in self._edges[tenant_id]
        }

        redirected = 0
        created_redirects: List[Dict[str, Any]] = []
        new_edges: List[Dict[str, Any]] = []
        for e in self._edges[tenant_id]:
            src, tgt = e["source_id"], e["target_id"]
            if src != secondary_id and tgt != secondary_id:
                new_edges.append(e)
                continue
            new_src = primary_id if src == secondary_id else src
            new_tgt = primary_id if tgt == secondary_id else tgt
            # Drop self-loops created by merge
            if new_src == new_tgt:
                redirected += 1
                continue
            key = (e["type"], new_src, new_tgt)
            dup = any(
                x["type"] == e["type"]
                and x["source_id"] == new_src
                and x["target_id"] == new_tgt
                for x in new_edges
            )
            if not dup:
                redirected_edge = {
                    "type": e["type"],
                    "source_id": new_src,
                    "target_id": new_tgt,
                    "properties": dict(e.get("properties") or {}),
                }
                new_edges.append(redirected_edge)
                # Only track as removable-on-split if it did not already exist
                if key not in existing_keys:
                    created_redirects.append(copy.deepcopy(redirected_edge))
            redirected += 1

        snapshot = {
            "secondary_node": sec_node,
            "edges": involving,
            "primary_id": primary_id,
            "secondary_id": secondary_id,
            "created_redirects": created_redirects,
        }
        self._merge_snapshots[f"{tenant_id}:{primary_id}:{secondary_id}"] = snapshot

        self._edges[tenant_id] = new_edges
        del nodes[secondary_id]
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
        snap = snapshot or self._merge_snapshots.get(
            f"{tenant_id}:{primary_id}:{secondary_id}"
        )
        if not snap:
            return {"restored": False, "edges_restored": 0}

        sec = snap["secondary_node"]
        self._nodes[tenant_id][secondary_id] = copy.deepcopy(sec)

        # Remove only edges that merge newly created on primary (not pre-existing)
        created_keys = {
            (e["type"], e["source_id"], e["target_id"])
            for e in snap.get("created_redirects") or []
        }
        cleaned: List[Dict[str, Any]] = []
        for e in self._edges[tenant_id]:
            key = (e["type"], e["source_id"], e["target_id"])
            if key in created_keys:
                continue
            cleaned.append(e)

        # Restore original secondary edges
        for oe in snap["edges"]:
            exists = any(
                x["type"] == oe["type"]
                and x["source_id"] == oe["source_id"]
                and x["target_id"] == oe["target_id"]
                for x in cleaned
            )
            if not exists:
                cleaned.append(copy.deepcopy(oe))

        self._edges[tenant_id] = cleaned
        return {"restored": True, "edges_restored": len(snap["edges"])}

    async def list_node_ids(
        self, tenant_id: str, label: Optional[str] = None
    ) -> List[str]:
        ids = []
        for nid, node in (self._nodes.get(tenant_id) or {}).items():
            if label is None or label in node["labels"]:
                ids.append(nid)
        return ids

    async def health(self) -> Tuple[bool, str]:
        return True, "mock"
