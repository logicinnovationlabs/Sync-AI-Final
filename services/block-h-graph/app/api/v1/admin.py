"""Admin merge/split Person operations (H3)."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.auth import assert_tenant_binding, require_scopes
from app.models import MergePersonsRequest, MergePersonsResponse, SplitPersonsRequest
from app.services.factory import get_graph_store
from app.services.graph_store import GraphStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])


def get_store() -> GraphStore:
    return get_graph_store()


@router.post("/admin/persons/merge", response_model=MergePersonsResponse)
async def merge_persons(
    body: MergePersonsRequest,
    current_user: Dict[str, Any] = Depends(require_scopes("graph.admin")),
    store: GraphStore = Depends(get_store),
) -> MergePersonsResponse:
    """Merge secondary Person into primary; redirect edges; delete secondary."""
    token_tenant = str(current_user.get("tenant_id") or "")
    tenant_id = body.tenant_id or token_tenant
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing")
    assert_tenant_binding(tenant_id, token_tenant)

    try:
        result = await store.merge_persons(
            tenant_id, body.primary_id, body.secondary_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("merge failed: %s", exc)
        raise HTTPException(status_code=503, detail="graph backend unavailable") from exc

    return MergePersonsResponse(
        primary_id=body.primary_id,
        secondary_id=body.secondary_id,
        edges_redirected=int(result.get("edges_redirected") or 0),
        secondary_deleted=bool(result.get("secondary_deleted")),
    )


@router.post("/admin/persons/split")
async def split_persons(
    body: SplitPersonsRequest,
    current_user: Dict[str, Any] = Depends(require_scopes("graph.admin")),
    store: GraphStore = Depends(get_store),
) -> Dict[str, Any]:
    """Restore a prior merge from snapshot (H3 integrity check)."""
    token_tenant = str(current_user.get("tenant_id") or "")
    tenant_id = body.tenant_id or token_tenant
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing")
    assert_tenant_binding(tenant_id, token_tenant)

    try:
        result = await store.split_persons(
            tenant_id, body.primary_id, body.secondary_id, snapshot=body.snapshot
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("split failed: %s", exc)
        raise HTTPException(status_code=503, detail="graph backend unavailable") from exc

    return {
        "primary_id": body.primary_id,
        "secondary_id": body.secondary_id,
        **result,
    }
