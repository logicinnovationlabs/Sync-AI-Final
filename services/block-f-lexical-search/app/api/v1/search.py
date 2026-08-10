"""POST /search/lexical — ACL-prefiltered BM25 retrieval."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.auth import assert_tenant_binding, get_current_user
from app.config import settings
from app.models.search_request import (
    FacetBucket,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.services.acl_filter import normalize_acl_terms
from app.services.factory import get_lexical_store
from app.services.lexical_store import LexicalStore
from app.services.metrics import record_acl_violation_attempt, record_query_latency, snapshot

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search"])


def get_store() -> LexicalStore:
    return get_lexical_store()


def _filters_dict(body: SearchRequest) -> Optional[Dict[str, Any]]:
    if not body.filters:
        return None
    raw = body.filters.model_dump(exclude_none=True)
    return raw or None


@router.post("/search/lexical", response_model=SearchResponse)
async def search_lexical(
    body: SearchRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    store: LexicalStore = Depends(get_store),
) -> SearchResponse:
    """
    Ranked lexical results with ACL filter applied BEFORE retrieval.

    Empty acl_terms => fail-closed empty result set.
    """
    token_tenant = str(current_user.get("tenant_id", ""))
    assert_tenant_binding(body.tenant_id, token_tenant)

    acl_terms = normalize_acl_terms(body.acl_terms)
    if not acl_terms:
        record_acl_violation_attempt()
        logger.warning(
            "ACL empty for user=%s tenant=%s — fail-closed",
            body.user_id,
            body.tenant_id,
        )
        return SearchResponse(results=[], facets={}, total=0, took_ms=0.0)

    size = min(body.size or settings.default_size, settings.max_size)
    started = time.perf_counter()
    try:
        raw = await store.search(
            tenant_id=body.tenant_id,
            query=body.query,
            acl_terms=acl_terms,
            filters=_filters_dict(body),
            facets=body.facets,
            from_=body.from_,
            size=size,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Lexical search failed: %s", exc)
        raise HTTPException(status_code=500, detail="lexical search failed") from exc
    finally:
        elapsed = time.perf_counter() - started
        record_query_latency(elapsed)

    took_ms = (time.perf_counter() - started) * 1000.0
    if took_ms > 200:
        logger.warning(
            "Performance outlier: took_ms=%.2f tenant=%s query_len=%d",
            took_ms,
            body.tenant_id,
            len(body.query or ""),
        )

    results = [
        SearchResult(
            document_id=r["document_id"],
            score=float(r["score"]),
            title=r.get("title") or "",
            snippet=r.get("snippet") or "",
            metadata=r.get("metadata"),
        )
        for r in raw.get("results") or []
    ]
    facets: Dict[str, list] = {}
    for field, buckets in (raw.get("facets") or {}).items():
        facets[field] = [
            FacetBucket(value=b["value"], count=int(b["count"])) for b in buckets
        ]

    logger.info(
        "lexical_search tenant=%s user=%s hits=%d took_ms=%.2f acl_terms=%d",
        body.tenant_id,
        body.user_id,
        len(results),
        took_ms,
        len(acl_terms),
    )
    return SearchResponse(
        results=results,
        facets=facets,
        total=int(raw.get("total") or 0),
        took_ms=round(took_ms, 3),
    )


@router.get("/search/metrics")
async def search_metrics() -> Dict[str, Any]:
    """Internal latency / ACL metrics snapshot."""
    return snapshot()