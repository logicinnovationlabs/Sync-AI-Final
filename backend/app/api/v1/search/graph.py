"""Block H: Knowledge Graph Search API."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, require_scope
from app.core.config import settings
from app.models.graph import (
    GraphNode,
    GraphRelationship,
    MergePersonsRequest,
    MergePersonsResponse,
    PeopleSearchResponse,
    PersonResult,
    RelatedResponse,
    SplitPersonsRequest,
    TraverseRequest,
    TraverseResponse,
)
from app.services.graph import GraphStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search-graph"])

# Metrics for observability
_METRICS: Dict[str, Any] = {
    "traverse_latency_seconds": [],
    "traverse_errors_total": 0,
}


def get_graph_store() -> GraphStore:
    """Factory to get graph store instance."""
    from app.core.config import settings

    if settings.graph_backend == "neo4j":
        from app.services.graph.neo4j_store import Neo4jGraphStore

        return Neo4jGraphStore()
    else:
        from app.services.graph.mock_store import MockGraphStore

        return MockGraphStore()


def assert_tenant_binding(requested_tenant: str, token_tenant: str) -> None:
    """Enforce tenant isolation in requests."""
    if token_tenant and requested_tenant != token_tenant:
        raise HTTPException(
            status_code=403, detail="Cannot access data from a different tenant"
        )


@router.post("/search/graph/traverse", response_model=TraverseResponse)
async def traverse_graph(
    body: TraverseRequest,
    current_user: Dict[str, Any] = Depends(require_scope("graph.read")),
    store: GraphStore = Depends(get_graph_store),
) -> TraverseResponse:
    """Expand relationships from a start node up to depth (max 2 for signoff)."""
    token_tenant = str(current_user.get("tenant_id") or "")
    tenant_id = body.tenant_id or token_tenant
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing")
    assert_tenant_binding(tenant_id, token_tenant)

    depth = min(body.depth, settings.max_traversal_depth)
    started = time.perf_counter()
    try:
        raw = await store.traverse(
            tenant_id=tenant_id,
            start_node_id=body.start_node_id,
            relationship_types=body.relationship_types,
            depth=depth,
            limit=settings.traversal_result_limit,
        )
    except Exception as exc:
        _METRICS["traverse_errors_total"] += 1
        logger.exception("traverse failed: %s", exc)
        raise HTTPException(status_code=503, detail="graph backend unavailable") from exc
    finally:
        elapsed = time.perf_counter() - started
        _METRICS["traverse_latency_seconds"].append(elapsed)
        if len(_METRICS["traverse_latency_seconds"]) > 5000:
            _METRICS["traverse_latency_seconds"] = _METRICS["traverse_latency_seconds"][
                -2500:
            ]

    nodes = [
        GraphNode(
            source_id=n["source_id"],
            labels=list(n.get("labels") or []),
            properties=dict(n.get("properties") or {}),
        )
        for n in raw.get("nodes") or []
    ]
    rels = [
        GraphRelationship(
            type=r["type"],
            source_id=r["source_id"],
            target_id=r["target_id"],
            properties=dict(r.get("properties") or {}),
        )
        for r in raw.get("relationships") or []
    ]
    return TraverseResponse(
        nodes=nodes,
        relationships=rels,
        start_node_id=body.start_node_id,
        depth=depth,
    )


@router.get("/search/graph/people", response_model=PeopleSearchResponse)
async def search_people(
    query: str = Query("", description="Search term for person name or email"),
    department: Optional[str] = Query(None, description="Filter by department"),
    team: Optional[str] = Query(None, description="Filter by team"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    current_user: Dict[str, Any] = Depends(require_scope("people.read")),
    store: GraphStore = Depends(get_graph_store),
) -> PeopleSearchResponse:
    """Search Person nodes by name/email/aliases with optional filters."""
    tenant_id = str(current_user.get("tenant_id") or "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing")

    try:
        results = await store.people_search(
            tenant_id=tenant_id,
            query=query,
            department=department,
            team=team,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("people_search failed: %s", exc)
        raise HTTPException(status_code=503, detail="graph backend unavailable") from exc

    persons = [PersonResult(**r) for r in results]
    return PeopleSearchResponse(results=persons, query=query, count=len(persons))


@router.get("/search/graph/related/{node_id}", response_model=RelatedResponse)
async def get_related(
    node_id: str,
    depth: int = Query(1, ge=1, le=2, description="Traversal depth"),
    limit: int = Query(50, ge=1, le=200, description="Max related nodes"),
    current_user: Dict[str, Any] = Depends(require_scope("graph.read")),
    store: GraphStore = Depends(get_graph_store),
) -> RelatedResponse:
    """Fetch nodes connected to the given node."""
    tenant_id = str(current_user.get("tenant_id") or "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing")

    try:
        related = await store.related(
            tenant_id=tenant_id,
            node_id=node_id,
            depth=depth,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("related failed: %s", exc)
        raise HTTPException(status_code=503, detail="graph backend unavailable") from exc

    return RelatedResponse(node_id=node_id, related=related, count=len(related))


@router.post("/search/graph/admin/merge", response_model=MergePersonsResponse)
async def merge_persons(
    body: MergePersonsRequest,
    current_user: Dict[str, Any] = Depends(require_scope("graph.admin")),
    store: GraphStore = Depends(get_graph_store),
) -> MergePersonsResponse:
    """Redirect all edges from secondary Person onto primary, then delete secondary."""
    token_tenant = str(current_user.get("tenant_id") or "")
    tenant_id = body.tenant_id or token_tenant
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing")
    assert_tenant_binding(tenant_id, token_tenant)

    try:
        result = await store.merge_persons(tenant_id, body.primary_id, body.secondary_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("merge_persons failed: %s", exc)
        raise HTTPException(status_code=503, detail="graph backend unavailable") from exc

    return MergePersonsResponse(
        primary_id=body.primary_id,
        secondary_id=body.secondary_id,
        edges_redirected=result["edges_redirected"],
        secondary_deleted=result["secondary_deleted"],
    )


@router.post("/search/graph/admin/split")
async def split_persons(
    body: SplitPersonsRequest,
    current_user: Dict[str, Any] = Depends(require_scope("graph.admin")),
    store: GraphStore = Depends(get_graph_store),
) -> Dict[str, Any]:
    """Restore a prior merge using a merge snapshot."""
    token_tenant = str(current_user.get("tenant_id") or "")
    tenant_id = body.tenant_id or token_tenant
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing")
    assert_tenant_binding(tenant_id, token_tenant)

    try:
        result = await store.split_persons(
            tenant_id, body.primary_id, body.secondary_id, body.snapshot
        )
    except Exception as exc:
        logger.exception("split_persons failed: %s", exc)
        raise HTTPException(status_code=503, detail="graph backend unavailable") from exc

    return result


@router.get("/search/graph/metrics")
async def graph_metrics() -> Dict[str, Any]:
    """Internal latency/error snapshot for observability."""
    samples = list(_METRICS["traverse_latency_seconds"])
    p95 = None
    if samples:
        ordered = sorted(samples)
        idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
        p95 = ordered[idx]
    return {
        "count": len(samples),
        "p95_seconds": p95,
        "errors_total": _METRICS["traverse_errors_total"],
    }
