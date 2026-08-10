"""GET /people/search - find principals by name or attributes."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import require_scopes
from app.config import settings
from app.models import PeopleSearchResponse, PersonResult
from app.services.factory import get_graph_store
from app.services.graph_store import GraphStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["people"])


def get_store() -> GraphStore:
    return get_graph_store()


@router.get("/people/search", response_model=PeopleSearchResponse)
async def people_search(
    q: str = Query("", description="Name / email / alias substring"),
    department: Optional[str] = Query(None),
    team: Optional[str] = Query(None),
    limit: int = Query(None, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(require_scopes("people.read")),
    store: GraphStore = Depends(get_store),
) -> PeopleSearchResponse:
    """Search Person nodes within the caller tenant."""
    tenant_id = str(current_user.get("tenant_id") or "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing")

    lim = limit or settings.people_search_limit
    try:
        raw = await store.people_search(
            tenant_id=tenant_id,
            query=q,
            department=department,
            team=team,
            limit=lim,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("people search failed: %s", exc)
        raise HTTPException(status_code=503, detail="graph backend unavailable") from exc

    results = [
        PersonResult(
            id=r["id"],
            display_name=r.get("display_name"),
            email=r.get("email"),
            title=r.get("title"),
            department=r.get("department"),
            team=r.get("team"),
            aliases=list(r.get("aliases") or []),
            properties=dict(r.get("properties") or {}),
        )
        for r in raw
    ]
    return PeopleSearchResponse(results=results, query=q, count=len(results))
