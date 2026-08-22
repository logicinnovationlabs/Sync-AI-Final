"""Block J: Federated Search API."""

from __future__ import annotations

import asyncio
import logging
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
        
        if settings.opensearch_url:
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
    query: str, tenant_id: str, acl_terms: List[str], size: int
) -> tuple[List[Dict[str, Any]], BackendStatus]:
    """Call vector search with error handling."""
    started = time.perf_counter()
    status = BackendStatus(name="vector", ok=False)
    
    try:
        from app.services.embedding import embedding_service
        from app.services.vector.qdrant_store import QdrantVectorStore
        from app.core.config import settings
        
        if settings.qdrant_url:
            query_embedding = await embedding_service.embed_text(query)
            if not query_embedding:
                raise ValueError("embedding service returned an empty vector")
            store = QdrantVectorStore()
            results = await store.search(
                tenant_id=tenant_id,
                query_embedding=query_embedding,
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


def _logical_document_id(doc: Dict[str, Any]) -> str:
    """Prefer the parent document id over a chunk hash / ``doc:chunk`` id."""
    raw = str(doc.get("document_id") or doc.get("id") or "").strip()
    chunk_id = str(doc.get("chunk_id") or "").strip()
    if raw and ":" in raw:
        parent, suffix = raw.split(":", 1)
        if parent and len(suffix) == 16 and all(c in "0123456789abcdef" for c in suffix.lower()):
            return parent
    if (not raw or (len(raw) == 16 and all(c in "0123456789abcdef" for c in raw.lower()))) and ":" in chunk_id:
        parent = chunk_id.split(":", 1)[0].strip()
        if parent:
            return parent
    return raw


def _payload_to_hit(payload: Dict[str, Any], score: float) -> Dict[str, Any]:
    body = str(payload.get("content") or payload.get("body_text") or payload.get("snippet") or "")
    doc_id = _logical_document_id(
        {
            "document_id": payload.get("document_id"),
            "id": payload.get("id"),
            "chunk_id": payload.get("chunk_id"),
        }
    )
    return {
        "document_id": doc_id,
        "title": str(payload.get("title") or doc_id or payload.get("id") or ""),
        "snippet": body[:400],
        "score": score,
        "sources": ["indexed"],
    }


async def _safe_call_indexed(
    query: str, tenant_id: str, acl_terms: List[str], size: int
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
            from app.services.embedding import embedding_service

            query_embedding = await embedding_service.embed_text(query)
            if not query_embedding:
                raise ValueError("embedding service returned an empty vector")
            scored = qdrant_client.client.search(
                collection_name=qdrant_client.collection_name,
                query_vector=query_embedding,
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
        doc_id = _logical_document_id(doc)
        if not doc_id:
            continue
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
        doc_id = _logical_document_id(doc)
        if not doc_id:
            continue
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
    
    tasks = [
        _safe_call_indexed(body.query, tenant_id, acl_terms, body.size),
    ]
    if body.enable_lexical:
        tasks.append(_safe_call_lexical(body.query, tenant_id, acl_terms, body.size))
    if body.enable_vector:
        tasks.append(_safe_call_vector(body.query, tenant_id, acl_terms, body.size))

    results = await asyncio.gather(*tasks)
    indexed_results = results[0][0]
    rest = results[1:]
    lexical_results: List[Dict[str, Any]] = []
    vector_results: List[Dict[str, Any]] = []
    if body.enable_lexical and rest:
        lexical_results = rest[0][0]
        rest = rest[1:]
    if body.enable_vector and rest:
        vector_results = rest[0][0]

    statuses = [r[1] for r in results]

    if not any(s.ok for s in statuses):
        raise HTTPException(status_code=503, detail="All search backends unavailable")

    merged = _merge_and_rank(
        indexed_results + lexical_results,
        vector_results,
        body.size,
    )
    
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
