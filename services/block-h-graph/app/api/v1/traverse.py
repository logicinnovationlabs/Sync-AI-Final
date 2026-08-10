"""POST /graph/traverse - depth-limited relationship expansion."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.auth import assert_tenant_binding, require_scopes
from app.config import settings
from app.models import GraphNode, GraphRelationship, TraverseRequest, TraverseResponse
from app.services.factory import get_graph_store
from app.services.graph_store import GraphStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["graph"])

_METRICS: Dict[str, Any] = {
    "traverse_latency_seconds": [],
    "traverse_errors_total": 0,
}


def get_store() -> GraphStore:
    return get_graph_store()


@router.post("/graph/traverse", response_model=TraverseResponse)
async def traverse_graph(
    body: TraverseRequest,
    current_user: Dict[str, Any] = Depends(require_scopes("graph.read")),
    store: GraphStore = Depends(get_store),
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
    except Exception as exc:  # noqa: BLE001
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


@router.get("/graph/metrics")
async def graph_metrics() -> Dict[str, Any]:
    """Internal latency/error snapshot for observability (Block O)."""
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
