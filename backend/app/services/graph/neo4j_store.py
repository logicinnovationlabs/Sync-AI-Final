"""Neo4j-backed graph store (Phase 2 integration)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from opentelemetry import trace

from app.core.config import settings
from app.services.graph.store import GraphStore
from app.services.graph.neo4j_client import get_neo4j_manager

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)

NODE_LABELS = [
    "Person",
    "Group",
    "Document",
    "Message",
    "Ticket",
    "CodeFile",
    "Repository",
    "Folder",
    "Team",
    "Project",
    "SourceSystem",
    "Topic",
    "Entity",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Neo4jGraphStore(GraphStore):
    """
    Real Neo4j implementation.

    Prefer one database per tenant; if the server cannot create DBs (Aura Free /
    Community), fall back to the default DB with mandatory tenant_id filters.
    """

    def __init__(self) -> None:
        self._mgr = get_neo4j_manager()
        self._constraints_ready: set[str] = set()
        self._merge_snapshots: Dict[str, Dict[str, Any]] = {}

    def _session(self, tenant_id: str):
        driver, cfg = self._mgr.get_driver(tenant_id)
        return driver.session(database=cfg.database), cfg

    async def ensure_tenant(self, tenant_id: str) -> None:
        if tenant_id in self._constraints_ready:
            return
        self._mgr.ensure_database(tenant_id)
        session, _ = self._session(tenant_id)
        try:
            for label in NODE_LABELS:
                # Composite uniqueness on (tenant_id, source_id)
                try:
                    session.run(
                        f"""
                        CREATE CONSTRAINT IF NOT EXISTS
                        FOR (n:{label})
                        REQUIRE (n.tenant_id, n.source_id) IS UNIQUE
                        """
                    )
                except Exception:  # noqa: BLE001
                    # Older Neo4j: create index instead
                    try:
                        session.run(
                            f"""
                            CREATE INDEX IF NOT EXISTS
                            FOR (n:{label}) ON (n.tenant_id, n.source_id)
                            """
                        )
                    except Exception as exc2:  # noqa: BLE001
                        logger.debug("index/constraint skip %s: %s", label, exc2)
            self._constraints_ready.add(tenant_id)
        finally:
            session.close()

    async def clear_tenant(self, tenant_id: str) -> None:
        await self.ensure_tenant(tenant_id)
        session, _ = self._session(tenant_id)
        try:
            session.run(
                "MATCH (n {tenant_id: $tenant}) DETACH DELETE n",
                tenant=tenant_id,
            )
        finally:
            session.close()

    async def upsert_node(
        self,
        tenant_id: str,
        label: str,
        source_id: str,
        properties: Dict[str, Any],
    ) -> None:
        with _tracer.start_as_current_span("neo4j.upsert_node") as span:
            span.set_attribute("db.system", "neo4j")
            span.set_attribute("db.operation", "upsert_node")
            span.set_attribute("tenant.id", tenant_id)
            await self.ensure_tenant(tenant_id)
            props = {k: v for k, v in properties.items() if v is not None}
            props["tenant_id"] = tenant_id
            props["source_id"] = source_id
            props.setdefault("created_at", _now())
            props["updated_at"] = props.get("updated_at") or _now()
            safe_label = label if label.isidentifier() else "Entity"
            cypher = f"""
            MERGE (n {{tenant_id: $tenant, source_id: $source_id}})
            ON CREATE SET n += $props
            ON MATCH SET
              n += CASE
                WHEN $props.updated_at IS NOT NULL AND n.updated_at IS NOT NULL
                     AND $props.updated_at < n.updated_at
                THEN {{}}
                ELSE $props
              END
            SET n:{safe_label}
            """
            session, _ = self._session(tenant_id)
            try:
                session.run(
                    cypher,
                    tenant=tenant_id,
                    source_id=source_id,
                    props=props,
                )
            finally:
                session.close()

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
        src_l = source_label if source_label and source_label.isidentifier() else "Entity"
        tgt_l = target_label if target_label and target_label.isidentifier() else "Entity"
        rel = "".join(c if c.isalnum() or c == "_" else "_" for c in rel_type.upper())
        props = dict(properties or {})
        cypher = f"""
        MERGE (a {{tenant_id: $tenant, source_id: $src}})
        ON CREATE SET a.created_at = $now, a.updated_at = $now
        SET a:{src_l}
        MERGE (b {{tenant_id: $tenant, source_id: $tgt}})
        ON CREATE SET b.created_at = $now, b.updated_at = $now
        SET b:{tgt_l}
        MERGE (a)-[r:{rel}]->(b)
        SET r += $props
        """
        session, _ = self._session(tenant_id)
        try:
            session.run(
                cypher,
                tenant=tenant_id,
                src=source_id,
                tgt=target_id,
                props=props,
                now=_now(),
            )
        finally:
            session.close()

    async def delete_node(self, tenant_id: str, source_id: str) -> bool:
        session, _ = self._session(tenant_id)
        try:
            result = session.run(
                """
                MATCH (n {tenant_id: $tenant, source_id: $id})
                WITH n, count(n) AS c
                DETACH DELETE n
                RETURN c
                """,
                tenant=tenant_id,
                id=source_id,
            )
            row = result.single()
            return bool(row and row["c"] > 0)
        finally:
            session.close()

    async def traverse(
        self,
        tenant_id: str,
        start_node_id: str,
        relationship_types: Optional[List[str]],
        depth: int,
        limit: int = 100,
    ) -> Dict[str, Any]:
        with _tracer.start_as_current_span("neo4j.traverse") as span:
            span.set_attribute("db.system", "neo4j")
            span.set_attribute("db.operation", "traverse")
            span.set_attribute("tenant.id", tenant_id)
            depth = min(depth, settings.max_traversal_depth)
            if relationship_types:
                rel_union = "|".join(
                    "".join(c if c.isalnum() or c == "_" else "_" for c in t.upper())
                    for t in relationship_types
                )
                rel_pattern = f"[*0..{depth}]"
                type_filter = f"ALL(rel IN relationships(path) WHERE type(rel) IN $types)"
                types = [
                    "".join(c if c.isalnum() or c == "_" else "_" for c in t.upper())
                    for t in relationship_types
                ]
            else:
                rel_pattern = f"[*0..{depth}]"
                type_filter = "true"
                types = []

            cypher = f"""
            MATCH (start {{tenant_id: $tenant, source_id: $start_id}})
            OPTIONAL MATCH path = (start)-{rel_pattern}-(end)
            WHERE end IS NULL OR (end.tenant_id = $tenant AND {type_filter})
            WITH collect(path) AS paths
            UNWIND paths AS path
            WITH path WHERE path IS NOT NULL
            WITH collect(DISTINCT path) AS paths2
            UNWIND paths2 AS path
            UNWIND nodes(path) AS n
            WITH collect(DISTINCT n) AS ns, paths2
            UNWIND paths2 AS path
            UNWIND relationships(path) AS rel
            WITH ns, collect(DISTINCT rel)[0..$limit] AS rs
            RETURN ns AS nodes, rs AS rels
            """
            session, _ = self._session(tenant_id)
            try:
                result = session.run(
                    cypher,
                    tenant=tenant_id,
                    start_id=start_node_id,
                    types=types,
                    limit=limit,
                )
                row = result.single()
                if not row or not row["nodes"]:
                    start = session.run(
                        "MATCH (n {tenant_id:$tenant, source_id:$id}) RETURN n",
                        tenant=tenant_id,
                        id=start_node_id,
                    ).single()
                    if not start:
                        return {"nodes": [], "relationships": []}
                    n = start["n"]
                    return {
                        "nodes": [
                            {
                                "source_id": n.get("source_id"),
                                "labels": list(n.labels),
                                "properties": dict(n),
                            }
                        ],
                        "relationships": [],
                    }

                nodes_out = []
                seen_n = set()
                for n in row["nodes"] or []:
                    sid = n.get("source_id")
                    if sid in seen_n:
                        continue
                    seen_n.add(sid)
                    nodes_out.append(
                        {
                            "source_id": sid,
                            "labels": list(n.labels),
                            "properties": dict(n),
                        }
                    )

                rels_out = []
                seen_r = set()
                for rel in row["rels"] or []:
                    start_node = rel.start_node
                    end_node = rel.end_node
                    key = (rel.type, start_node.get("source_id"), end_node.get("source_id"))
                    if key in seen_r:
                        continue
                    seen_r.add(key)
                    rels_out.append(
                        {
                            "type": rel.type,
                            "source_id": start_node.get("source_id"),
                            "target_id": end_node.get("source_id"),
                            "properties": dict(rel),
                        }
                    )
                return {"nodes": nodes_out, "relationships": rels_out[:limit]}
            finally:
                session.close()

    async def people_search(
        self,
        tenant_id: str,
        query: str,
        department: Optional[str] = None,
        team: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        cypher = """
        MATCH (p:Person {tenant_id: $tenant})
        WHERE ($q = '' OR
               toLower(coalesce(p.display_name,'')) CONTAINS $q OR
               toLower(coalesce(p.email,'')) CONTAINS $q OR
               ANY(alias IN coalesce(p.aliases, []) WHERE toLower(alias) CONTAINS $q))
          AND ($department IS NULL OR p.department = $department)
          AND ($team IS NULL OR p.team = $team)
        RETURN p
        LIMIT $limit
        """
        session, _ = self._session(tenant_id)
        try:
            result = session.run(
                cypher,
                tenant=tenant_id,
                q=(query or "").lower(),
                department=department,
                team=team,
                limit=limit,
            )
            out = []
            for record in result:
                p = record["p"]
                props = dict(p)
                out.append(
                    {
                        "id": props.get("source_id"),
                        "display_name": props.get("display_name"),
                        "email": props.get("email"),
                        "title": props.get("title"),
                        "department": props.get("department"),
                        "team": props.get("team"),
                        "aliases": list(props.get("aliases") or []),
                        "properties": props,
                    }
                )
            return out
        finally:
            session.close()

    async def related(
        self,
        tenant_id: str,
        node_id: str,
        depth: int = 1,
        limit: int = 50,
        relationship_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        if relationship_types:
            rel_union = "|".join(
                "".join(c if c.isalnum() or c == "_" else "_" for c in t.upper())
                for t in relationship_types
            )
            pattern = f"[r:{rel_union}]"
        else:
            pattern = "[r]"

        cypher = f"""
        MATCH (n {{tenant_id: $tenant, source_id: $id}})-{pattern}-(related)
        WHERE related.tenant_id = $tenant
        RETURN related, type(r) AS rel_type
        LIMIT $limit
        """
        session, _ = self._session(tenant_id)
        try:
            result = session.run(
                cypher, tenant=tenant_id, id=node_id, limit=limit
            )
            out = []
            for record in result:
                related = record["related"]
                out.append(
                    {
                        "related": {
                            "source_id": related.get("source_id"),
                            "labels": list(related.labels),
                            "properties": dict(related),
                        },
                        "rel_type": record["rel_type"],
                    }
                )
            return out
        finally:
            session.close()

    async def count_edges_by_type(self, tenant_id: str) -> Dict[str, int]:
        cypher = """
        MATCH (a {tenant_id: $tenant})-[r]->(b {tenant_id: $tenant})
        RETURN type(r) AS t, count(r) AS c
        """
        session, _ = self._session(tenant_id)
        try:
            result = session.run(cypher, tenant=tenant_id)
            return {row["t"]: row["c"] for row in result}
        finally:
            session.close()

    async def get_edges_involving(
        self, tenant_id: str, source_id: str
    ) -> List[Dict[str, Any]]:
        cypher = """
        MATCH (a {tenant_id: $tenant})-[r]->(b {tenant_id: $tenant})
        WHERE a.source_id = $id OR b.source_id = $id
        RETURN DISTINCT type(r) AS type,
               a.source_id AS source_id,
               b.source_id AS target_id,
               properties(r) AS properties
        """
        session, _ = self._session(tenant_id)
        try:
            result = session.run(cypher, tenant=tenant_id, id=source_id)
            return [
                {
                    "type": row["type"],
                    "source_id": row["source_id"],
                    "target_id": row["target_id"],
                    "properties": dict(row["properties"] or {}),
                }
                for row in result
            ]
        finally:
            session.close()

    async def merge_persons(
        self, tenant_id: str, primary_id: str, secondary_id: str
    ) -> Dict[str, Any]:
        involving = await self.get_edges_involving(tenant_id, secondary_id)
        session, _ = self._session(tenant_id)
        try:
            sec = session.run(
                "MATCH (p:Person {tenant_id:$t, source_id:$id}) RETURN p",
                t=tenant_id,
                id=secondary_id,
            ).single()
            if not sec:
                raise KeyError("secondary Person not found")
            prim = session.run(
                "MATCH (p:Person {tenant_id:$t, source_id:$id}) RETURN p",
                t=tenant_id,
                id=primary_id,
            ).single()
            if not prim:
                raise KeyError("primary Person not found")

            existing = await self.get_edges_involving(tenant_id, primary_id)
            existing_keys = {
                (e["type"], e["source_id"], e["target_id"]) for e in existing
            }
            created_redirects = []
            for e in involving:
                new_src = primary_id if e["source_id"] == secondary_id else e["source_id"]
                new_tgt = primary_id if e["target_id"] == secondary_id else e["target_id"]
                if new_src == new_tgt:
                    continue
                key = (e["type"], new_src, new_tgt)
                if key not in existing_keys:
                    created_redirects.append(
                        {
                            "type": e["type"],
                            "source_id": new_src,
                            "target_id": new_tgt,
                            "properties": dict(e.get("properties") or {}),
                        }
                    )

            snapshot = {
                "secondary_node": {
                    "source_id": secondary_id,
                    "labels": list(sec["p"].labels),
                    "properties": dict(sec["p"]),
                },
                "edges": involving,
                "primary_id": primary_id,
                "secondary_id": secondary_id,
                "created_redirects": created_redirects,
            }
            self._merge_snapshots[f"{tenant_id}:{primary_id}:{secondary_id}"] = snapshot
        finally:
            session.close()

        for e in involving:
            new_src = primary_id if e["source_id"] == secondary_id else e["source_id"]
            new_tgt = primary_id if e["target_id"] == secondary_id else e["target_id"]
            if new_src == new_tgt:
                continue
            await self.upsert_edge(
                tenant_id,
                e["type"],
                new_src,
                new_tgt,
                e.get("properties"),
                source_label="Person" if new_src == primary_id else None,
                target_label="Person" if new_tgt == primary_id else None,
            )
        await self.delete_node(tenant_id, secondary_id)

        return {
            "edges_redirected": len(involving),
            "secondary_deleted": True,
            "snapshot": self._merge_snapshots.get(
                f"{tenant_id}:{primary_id}:{secondary_id}"
            ),
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
        label = (sec.get("labels") or ["Person"])[0]
        await self.upsert_node(
            tenant_id, label, secondary_id, sec.get("properties") or {}
        )

        for e in snap.get("created_redirects") or []:
            session, _ = self._session(tenant_id)
            try:
                rel = "".join(
                    c if c.isalnum() or c == "_" else "_" for c in e["type"].upper()
                )
                session.run(
                    f"""
                    MATCH (a {{tenant_id: $t, source_id: $s}})-[r:{rel}]->(b {{tenant_id: $t, source_id: $tg}})
                    DELETE r
                    """,
                    t=tenant_id,
                    s=e["source_id"],
                    tg=e["target_id"],
                )
            finally:
                session.close()

        for e in snap["edges"]:
            await self.upsert_edge(
                tenant_id,
                e["type"],
                e["source_id"],
                e["target_id"],
                e.get("properties"),
            )
        return {"restored": True, "edges_restored": len(snap["edges"])}

    async def list_node_ids(
        self, tenant_id: str, label: Optional[str] = None
    ) -> List[str]:
        if label and label.isidentifier():
            cypher = f"MATCH (n:{label} {{tenant_id:$t}}) RETURN n.source_id AS id"
        else:
            cypher = "MATCH (n {tenant_id:$t}) RETURN n.source_id AS id"
        session, _ = self._session(tenant_id)
        try:
            return [row["id"] for row in session.run(cypher, t=tenant_id)]
        finally:
            session.close()

    async def health(self) -> Tuple[bool, str]:
        return self._mgr.health()
