"""GET /graph/related/{node_id} - related-entity lookup."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import require_scopes
from app.config import settings
from app.models import RelatedResponse
from app.services.factory import get_graph_store
from app.services.graph_store import GraphStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["graph"])


def get_store() -> GraphStore:
    return get_graph_store()


@router.get("/graph/related/{node_id}", response_model=RelatedResponse)
async def related_entities(
    node_id: str,
    depth: int = Query(1, ge=0, le=2),
    limit: int = Query(None, ge=1, le=200),
    relationship_types: Optional[str] = Query(
        None, description="Comma-separated relationship types"
    ),
    current_user: Dict[str, Any] = Depends(require_scopes("graph.read")),
    store: GraphStore = Depends(get_store),
) -> RelatedResponse:
    """Fetch nodes connected to node_id within the caller tenant."""
    tenant_id = str(current_user.get("tenant_id") or "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing")

    lim = limit or settings.related_default_limit
    rel_types: Optional[List[str]] = None
    if relationship_types:
        rel_types = [t.strip() for t in relationship_types.split(",") if t.strip()]

    try:
        raw = await store.related(
            tenant_id=tenant_id,
            node_id=node_id,
            depth=depth,
            limit=lim,
            relationship_types=rel_types,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("related lookup failed: %s", exc)
        raise HTTPException(status_code=503, detail="graph backend unavailable") from exc

    return RelatedResponse(node_id=node_id, related=raw, count=len(raw))
