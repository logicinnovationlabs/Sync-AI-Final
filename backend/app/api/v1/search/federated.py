"""Block J: Federated Search API."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, require_scope
from app.acl.filter import is_fail_closed
from app.models.federated import (
    BackendStatus,
    FederatedSearchRequest,
    FederatedSearchResponse,
    ResultItem,
    UserContext,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search-federated"])


async def _safe_call_lexical(
    query: str, tenant_id: str, acl_terms: List[str], size: int
) -> tuple[List[Dict[str, Any]], BackendStatus]:
    """Call lexical search with error handling."""
    started = time.perf_counter()
    status = BackendStatus(name="lexical", ok=False)
    
    try:
        # Import locally to avoid circular dependency
        from app.services.lexical.opensearch_store import OpenSearchStore
        from app.core.config import settings
        
        if settings.opensearch_url:
            store = OpenSearchStore()
            results = await store.search(
                tenant_id=tenant_id,
                query=query,
                acl_terms=acl_terms,
                size=size * 2,  # Over-fetch for fusion
            )
            status.ok = True
            status.hit_count = len(results)
            return results, status
    except Exception as exc:
        logger.warning("Lexical search failed: %s", exc)
        status.error = str(exc)
    finally:
        status.latency_ms = (time.perf_counter() - started) * 1000
    
    return [], status


async def _safe_call_vector(
    query: str, tenant_id: str, acl_terms: List[str], size: int
) -> tuple[List[Dict[str, Any]], BackendStatus]:
    """Call vector search with error handling."""
    started = time.perf_counter()
    status = BackendStatus(name="vector", ok=False)
    
    try:
        from app.services.vector.qdrant_store import QdrantVectorStore
        from app.core.config import settings
        
        if settings.qdrant_url:
            store = QdrantVectorStore()
            results = await store.search(
                tenant_id=tenant_id,
                query_vector=[],  # Would need embedding service
                acl_terms=acl_terms,
                limit=size * 2,
            )
            status.ok = True
            status.hit_count = len(results)
            return results, status
    except Exception as exc:
        logger.warning("Vector search failed: %s", exc)
        status.error = str(exc)
    finally:
        status.latency_ms = (time.perf_counter() - started) * 1000
    
    return [], status


def _merge_and_rank(
    lexical_results: List[Dict[str, Any]],
    vector_results: List[Dict[str, Any]],
    size: int,
) -> List[ResultItem]:
    """Merge and rank results using reciprocal rank fusion."""
    # Simple RRF fusion
    scores: Dict[str, float] = {}
    metadata: Dict[str, Dict[str, Any]] = {}
    
    k = 60  # RRF constant
    
    for rank, doc in enumerate(lexical_results, 1):
        doc_id = doc.get("document_id") or doc.get("id", "")
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        if doc_id not in metadata:
            metadata[doc_id] = {
                "title": doc.get("title", ""),
                "snippet": doc.get("snippet", ""),
                "lexical_score": doc.get("score", 0),
                "sources": ["lexical"],
            }
        else:
            metadata[doc_id]["sources"].append("lexical")
    
    for rank, doc in enumerate(vector_results, 1):
        doc_id = doc.get("document_id") or doc.get("id", "")
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        if doc_id not in metadata:
            metadata[doc_id] = {
                "title": doc.get("title", ""),
                "snippet": doc.get("snippet", ""),
                "vector_score": doc.get("score", 0),
                "sources": ["vector"],
            }
        else:
            metadata[doc_id]["sources"].append("vector")
            metadata[doc_id]["vector_score"] = doc.get("score", 0)
    
    # Sort by fusion score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:size]
    
    return [
        ResultItem(
            document_id=doc_id,
            score=score,
            fusion_score=score,
            title=metadata[doc_id].get("title", ""),
            snippet=metadata[doc_id].get("snippet", ""),
            sources=metadata[doc_id].get("sources", []),
            lexical_score=metadata[doc_id].get("lexical_score"),
            vector_score=metadata[doc_id].get("vector_score"),
        )
        for doc_id, score in ranked
    ]


@router.post("/search/federated", response_model=FederatedSearchResponse)
async def federated_search(
    body: FederatedSearchRequest,
    current_user: Dict[str, Any] = Depends(require_scope("search.read")),
) -> FederatedSearchResponse:
    """
    Federated search across lexical and vector backends.
    
    Orchestrates parallel searches and merges results using reciprocal rank fusion.
    Gracefully degrades when individual backends fail.
    """
    started = time.perf_counter()
    
    tenant_id = str(current_user.get("tenant_id") or "")
    if body.tenant_id and body.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    
    # Build ACL terms from user context
    user_ctx = UserContext(
        tenant_id=tenant_id,
        principal_id=str(current_user.get("sub") or current_user.get("principal_id", "")),
        groups=current_user.get("groups", []),
        scopes=current_user.get("scopes", []),
    )
    acl_terms = user_ctx.build_acl_terms()
    if is_fail_closed(acl_terms):
        return FederatedSearchResponse(
            results=[],
            total=0,
            took_ms=0.0,
            degraded=False,
            backends=[],
            query=body.query,
        )
    
    # Fan-out to backends concurrently
    tasks = []
    if body.enable_lexical:
        tasks.append(_safe_call_lexical(body.query, tenant_id, acl_terms, body.size))
    if body.enable_vector:
        tasks.append(_safe_call_vector(body.query, tenant_id, acl_terms, body.size))
    
    if not tasks:
        raise HTTPException(status_code=400, detail="No search backends enabled")
    
    results = await asyncio.gather(*tasks)
    
    # Extract results and statuses
    lexical_results = results[0][0] if body.enable_lexical else []
    vector_results = results[1][0] if body.enable_vector and len(results) > 1 else []
    
    statuses = [r[1] for r in results]
    
    # Check if all backends failed
    if not any(s.ok for s in statuses):
        raise HTTPException(status_code=503, detail="All search backends unavailable")
    
    # Merge and rank
    merged = _merge_and_rank(lexical_results, vector_results, body.size)
    
    # Pagination
    start = body.from_
    end = start + body.size
    page = merged[start:end]
    
    took_ms = (time.perf_counter() - started) * 1000
    degraded = not all(s.ok for s in statuses)
    
    return FederatedSearchResponse(
        results=page,
        total=len(merged),
        took_ms=took_ms,
        degraded=degraded,
        backends=statuses,
        query=body.query,
    )


@router.get("/search/federated/health")
async def federated_health() -> Dict[str, Any]:
    """Health check for federated search."""
    from app.core.config import settings
    
    backends = {
        "lexical": bool(settings.opensearch_url),
        "vector": bool(settings.qdrant_url),
        "graph": bool(settings.neo4j_uri),
    }
    
    return {
        "status": "healthy",
        "backends_configured": backends,
    }
