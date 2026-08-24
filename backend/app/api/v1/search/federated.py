"""Block J: Federated Search API."""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_scope
from app.acl.filter import acl_terms_from_jwt, document_is_visible, is_fail_closed
from app.models.federated import (
    BackendStatus,
    FederatedSearchRequest,
    FederatedSearchResponse,
    ResultItem,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search-federated"])


async def _query_embedding_for_search(query: str) -> Optional[List[float]]:
    """One Gemini call shared by indexed + vector backends."""
    if not query or query.strip() in {"*", "all"}:
        return None
    try:
        from app.services.embedding import embedding_service

        vec = await embedding_service.embed_text(query)
        return list(vec) if vec else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Shared query embedding failed: %s", exc)
        return None


async def _safe_call_lexical(
    query: str, tenant_id: str, acl_terms: List[str], size: int
) -> tuple[List[Dict[str, Any]], BackendStatus]:
    """Call lexical search with error handling."""
    started = time.perf_counter()
    status = BackendStatus(name="lexical", ok=False)
    
    try:
        # Import locally to avoid circular dependency
        from app.services.lexical.opensearch_store import OpenSearchLexicalStore
        from app.core.config import settings
        
        if settings.opensearch_url or settings.lexical_search_url:
            store = OpenSearchLexicalStore()
            payload = await store.search(
                tenant_id=tenant_id,
                query=query,
                acl_terms=acl_terms,
                size=size * 2,  # Over-fetch for fusion
            )
            results = payload.get("results", []) if isinstance(payload, dict) else list(payload or [])
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
    query: str,
    tenant_id: str,
    acl_terms: List[str],
    size: int,
    query_embedding: Optional[List[float]] = None,
) -> tuple[List[Dict[str, Any]], BackendStatus]:
    """Call vector search with error handling."""
    started = time.perf_counter()
    status = BackendStatus(name="vector", ok=False)
    
    try:
        from app.services.embedding import embedding_service
        from app.services.vector.qdrant_store import QdrantVectorStore
        from app.core.config import settings
        
        if settings.qdrant_url:
            vec = list(query_embedding) if query_embedding else None
            if not vec:
                vec = await embedding_service.embed_text(query)
            if not vec:
                raise ValueError("embedding service returned an empty vector")
            store = QdrantVectorStore()
            results = await store.search(
                tenant_id=tenant_id,
                query_embedding=vec,
                acl_terms=acl_terms,
                top_k=size * 2,
            )
            for doc in results:
                if not doc.get("snippet"):
                    doc["snippet"] = doc.get("chunk_text") or ""
            status.ok = True
            status.hit_count = len(results)
            return results, status
    except Exception as exc:
        logger.warning("Vector search failed: %s", exc)
        status.error = str(exc)
    finally:
        status.latency_ms = (time.perf_counter() - started) * 1000
    
    return [], status


def _payload_to_hit(payload: Dict[str, Any], score: float) -> Dict[str, Any]:
    body = str(payload.get("content") or payload.get("body_text") or payload.get("snippet") or "")
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)
    body = re.sub(r"\s+", " ", body).strip()
    return {
        "document_id": str(payload.get("id") or payload.get("document_id") or ""),
        "title": str(payload.get("title") or payload.get("id") or ""),
        "snippet": body[:400],
        "score": score,
        "sources": ["indexed"],
    }


async def _safe_call_indexed(
    query: str,
    tenant_id: str,
    acl_terms: List[str],
    size: int,
    query_embedding: Optional[List[float]] = None,
) -> tuple[List[Dict[str, Any]], BackendStatus]:
    """Read the Block B `documents` collection that Celery actually upserts."""
    started = time.perf_counter()
    status = BackendStatus(name="indexed", ok=False)
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        from app.storage.qdrant_client import qdrant_client

        tenant_filter = Filter(
            must=[
                FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant_id)))
            ]
        )
        hits: List[Dict[str, Any]] = []
        browse = not query or query.strip() in {"*", "all"}
        if browse:
            points, _ = qdrant_client.client.scroll(
                collection_name=qdrant_client.collection_name,
                scroll_filter=tenant_filter,
                limit=size * 2,
                with_payload=True,
                with_vectors=False,
            )
            raw = [(p.payload or {}, 1.0) for p in points]
        else:
            vec = list(query_embedding) if query_embedding else None
            if not vec:
                from app.services.embedding import embedding_service

                vec = await embedding_service.embed_text(query)
            if not vec:
                raise ValueError("embedding service returned an empty vector")
            scored = qdrant_client.client.search(
                collection_name=qdrant_client.collection_name,
                query_vector=vec,
                query_filter=tenant_filter,
                limit=size * 2,
            )
            raw = [(p.payload or {}, float(p.score or 0.0)) for p in scored]

        for payload, score in raw:
            if not document_is_visible(
                acl_terms, payload.get("permissions") or payload.get("acl_terms")
            ):
                continue
            hit = _payload_to_hit(payload, score)
            if hit["document_id"]:
                hits.append(hit)
        status.ok = True
        status.hit_count = len(hits)
        return hits, status
    except Exception as exc:
        logger.warning("Indexed collection search failed: %s", exc)
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


async def run_federated_backends(
    query: str,
    tenant_id: str,
    acl_terms: List[str],
    size: int,
    *,
    enable_lexical: bool = True,
    enable_vector: bool = True,
) -> tuple[List[ResultItem], List[BackendStatus]]:
    """Parallel indexed + lexical + vector with a single shared query embedding."""
    embedding = await _query_embedding_for_search(query)
    tasks = [
        _safe_call_indexed(
            query, tenant_id, acl_terms, size, query_embedding=embedding
        )
    ]
    if enable_lexical:
        tasks.append(_safe_call_lexical(query, tenant_id, acl_terms, size))
    if enable_vector:
        tasks.append(
            _safe_call_vector(
                query, tenant_id, acl_terms, size, query_embedding=embedding
            )
        )
    results = await asyncio.gather(*tasks)
    indexed_results = results[0][0]
    rest = results[1:]
    lexical_results: List[Dict[str, Any]] = []
    vector_results: List[Dict[str, Any]] = []
    if enable_lexical and rest:
        lexical_results = rest[0][0]
        rest = rest[1:]
    if enable_vector and rest:
        vector_results = rest[0][0]
    statuses = [r[1] for r in results]
    merged = _merge_and_rank(
        indexed_results + lexical_results,
        vector_results,
        size,
    )
    return merged, statuses


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
    
    acl_terms = acl_terms_from_jwt(current_user)
    if is_fail_closed(acl_terms):
        return FederatedSearchResponse(
            results=[],
            total=0,
            took_ms=0.0,
            degraded=False,
            backends=[],
            query=body.query,
        )
    
    merged, statuses = await run_federated_backends(
        body.query,
        tenant_id,
        acl_terms,
        body.size,
        enable_lexical=body.enable_lexical,
        enable_vector=body.enable_vector,
    )

    if not any(s.ok for s in statuses):
        raise HTTPException(status_code=503, detail="All search backends unavailable")
    
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
        "lexical": bool(settings.opensearch_url or settings.lexical_search_url),
        "vector": bool(settings.qdrant_url),
        "graph": bool(settings.neo4j_uri),
    }
    
    return {
        "status": "healthy",
        "backends_configured": backends,
    }
