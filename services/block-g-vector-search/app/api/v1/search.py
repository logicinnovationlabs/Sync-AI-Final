"""POST /api/v1/search/vector — ACL-prefiltered ANN retrieval for Block J."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.auth import assert_tenant_binding, get_current_user
from app.config import settings
from app.models.search_request import SearchRequest, SearchResponse, SearchResult
from app.services.acl_filter import normalize_acl_terms
from app.services.factory import get_vector_store
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search"])

_METRICS: Dict[str, Any] = {
    "vector_query_latency_seconds": [],
    "vector_query_errors_total": 0,
}


def get_store() -> VectorStore:
    return get_vector_store()


@router.post("/search/vector", response_model=SearchResponse)
async def search_vector(
    body: SearchRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    store: VectorStore = Depends(get_store),
) -> SearchResponse:
    """
    Ranked semantic candidates with tenant binding + ACL prefilter.

    Scores from different model_version values must not be compared by callers;
    each result carries its model_version and the response lists versions used.
    """
    token_tenant = str(current_user.get("tenant_id", ""))
    assert_tenant_binding(body.tenant_id, token_tenant)

    if not body.query_embedding:
        raise HTTPException(status_code=400, detail="query_embedding is required")

    acl_terms = normalize_acl_terms(body.acl_terms)
    if not acl_terms:
        return SearchResponse(results=[], model_versions_used=[])

    top_k = min(body.top_k or settings.default_top_k, settings.max_top_k)
    started = time.perf_counter()
    try:
        raw = await store.search(
            tenant_id=body.tenant_id,
            query_embedding=body.query_embedding,
            acl_terms=acl_terms,
            top_k=top_k,
            model_version=body.model_version,
            score_threshold=body.score_threshold,
        )
    except Exception as exc:
        _METRICS["vector_query_errors_total"] += 1
        logger.exception("vector search failed: %s", exc)
        raise HTTPException(status_code=500, detail="vector search failed") from exc
    finally:
        elapsed = time.perf_counter() - started
        _METRICS["vector_query_latency_seconds"].append(elapsed)
        if len(_METRICS["vector_query_latency_seconds"]) > 10_000:
            _METRICS["vector_query_latency_seconds"] = _METRICS[
                "vector_query_latency_seconds"
            ][-5000:]

    results = [
        SearchResult(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            score=float(r["score"]),
            model_version=r["model_version"],
            chunk_text=r.get("chunk_text", ""),
            metadata=r.get("metadata"),
        )
        for r in raw
    ]
    versions = sorted({r.model_version for r in results if r.model_version})
    return SearchResponse(results=results, model_versions_used=versions)


@router.get("/search/metrics")
async def search_metrics() -> Dict[str, Any]:
    """Internal latency/error snapshot for observability smoke checks."""
    samples = list(_METRICS["vector_query_latency_seconds"])
    p95 = None
    if samples:
        ordered = sorted(samples)
        idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
        p95 = ordered[idx]
    return {
        "count": len(samples),
        "p95_seconds": p95,
        "errors_total": _METRICS["vector_query_errors_total"],
    }