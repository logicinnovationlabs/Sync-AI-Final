"""Block J: Federated Search API."""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.services.rag_debug_trace import get_tracer as _get_rag_tracer

from app.api.deps import require_scope, get_tenant_session
from app.acl.filter import acl_terms_from_jwt, document_is_visible, is_fail_closed, filter_results_with_admin_overrides
from app.models.federated import (
    BackendStatus,
    FederatedSearchRequest,
    FederatedSearchResponse,
    ResultItem,
)
from app.services.admin.access_override_service import access_override_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search-federated"])


async def _query_embedding_for_search(query: str) -> Optional[List[float]]:
    """One Gemini call shared by indexed + vector backends."""
    if not query or query.strip() in {"*", "all"}:
        return None
    try:
        from app.services.embedding import embedding_service

        # Phase 1: always embed queries with retrieval_query task type.
        vec = await embedding_service.embed_query(query)

        # --- Rule #2, Stage 3: query embedding model + dimension ---
        tracer = _get_rag_tracer()
        model_name = getattr(embedding_service.provider, "model", "unknown")
        model_version = str(
            getattr(embedding_service.provider, "model", "")
            or getattr(embedding_service.provider, "name", "unknown")
        )
        dimension = len(vec) if vec else 0
        tracer.log_query_embedding(model_name, model_version, dimension)

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

            # --- Rule #2, Stage 4: lexical retrieval ---
            tracer = _get_rag_tracer()
            tracer.log_lexical_retrieval(query, results)

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
                vec = await embedding_service.embed_query(query)
            if not vec:
                raise ValueError("embedding service returned an empty vector")
            store = QdrantVectorStore()
            results = await store.search(
                tenant_id=tenant_id,
                query_embedding=vec,
                acl_terms=acl_terms,
                top_k=size * 2,
            )
            enriched: List[Dict[str, Any]] = []
            for doc in results:
                meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
                snippet = (
                    doc.get("snippet")
                    or doc.get("chunk_text")
                    or ""
                )
                # Phase 1 sent ~1000 chars/source to the LLM; keep more for stories.
                if isinstance(snippet, str) and len(snippet) > 4000:
                    snippet = snippet[:4000]
                hit = dict(doc)
                hit["snippet"] = snippet
                hit["title"] = str(doc.get("title") or meta.get("title") or "")
                hit["from_email"] = str(
                    doc.get("from_email") or meta.get("from_email") or ""
                )
                hit["source_type"] = str(
                    doc.get("source_type") or meta.get("source_type") or ""
                )
                if meta:
                    hit["metadata"] = meta
                enriched.append(hit)
            status.ok = True
            status.hit_count = len(enriched)
            return enriched, status
    except Exception as exc:
        logger.warning("Vector search failed: %s", exc)
        status.error = str(exc)
    finally:
        status.latency_ms = (time.perf_counter() - started) * 1000
    
    return [], status


def _structured_meta(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("structured_metadata")
    if isinstance(raw, dict):
        return raw
    nested = payload.get("metadata")
    if isinstance(nested, dict):
        inner = nested.get("structured_metadata")
        if isinstance(inner, dict):
            return inner
        return nested
    return {}


def _payload_to_hit(payload: Dict[str, Any], score: float) -> Dict[str, Any]:
    body = str(payload.get("content") or payload.get("body_text") or payload.get("snippet") or "")
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)
    body = re.sub(r"\s+", " ", body).strip()
    meta = _structured_meta(payload)
    from_email = str(
        payload.get("from_email")
        or meta.get("from_email")
        or meta.get("from")
        or ""
    )
    subject = str(payload.get("subject") or meta.get("subject") or "")
    source_type = str(
        payload.get("source_type") or meta.get("source_type") or payload.get("source") or ""
    )
    hit_meta: Dict[str, Any] = {}
    if from_email:
        hit_meta["from_email"] = from_email
    if subject:
        hit_meta["subject"] = subject
    if source_type:
        hit_meta["source_type"] = source_type
    to_emails = meta.get("to_emails")
    if to_emails:
        hit_meta["to_emails"] = to_emails
    return {
        "document_id": str(payload.get("id") or payload.get("document_id") or ""),
        "title": str(payload.get("title") or subject or payload.get("id") or ""),
        # Phase 1 passed chunk text (~1000+) into the LLM — keep a full passage.
        "snippet": body[:6000],
        "score": score,
        "sources": ["indexed"],
        "from_email": from_email,
        "source_type": source_type,
        "metadata": hit_meta or None,
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

                vec = await embedding_service.embed_query(query)
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


def _prefer_snippet(existing: str, candidate: str) -> str:
    """Keep the longer usable snippet when fusing backends."""
    a = (existing or "").strip()
    b = (candidate or "").strip()
    if len(b) > len(a):
        return b
    return a


def _ingest_hit_meta(bucket: Dict[str, Any], doc: Dict[str, Any]) -> None:
    """Merge title/snippet/from into the fusion metadata bucket."""
    title = str(doc.get("title") or "")
    if title and (not bucket.get("title") or len(title) > len(str(bucket.get("title") or ""))):
        bucket["title"] = title
    bucket["snippet"] = _prefer_snippet(str(bucket.get("snippet") or ""), str(doc.get("snippet") or ""))
    from_email = str(doc.get("from_email") or "")
    if not from_email:
        meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        from_email = str(meta.get("from_email") or meta.get("from") or "")
    if from_email and not bucket.get("from_email"):
        bucket["from_email"] = from_email
    source_type = str(doc.get("source_type") or doc.get("source") or "")
    if not source_type:
        meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        source_type = str(meta.get("source_type") or meta.get("source") or "")
    if source_type and not bucket.get("source_type"):
        bucket["source_type"] = source_type
    extra = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else None
    if extra:
        merged_meta = dict(bucket.get("metadata") or {})
        merged_meta.update({k: v for k, v in extra.items() if v not in (None, "", [])})
        bucket["metadata"] = merged_meta


def _merge_and_rank(
    lexical_results: List[Dict[str, Any]],
    vector_results: List[Dict[str, Any]],
    size: int,
    indexed_results: Optional[List[Dict[str, Any]]] = None,
) -> List[ResultItem]:
    """Merge and rank results using reciprocal rank fusion.

    Each backend is its own RRF stream. Concatenating indexed+lexical into one
    list buried connector-specific lexical hits (e.g. SharePoint) under a long
    Qdrant documents ranking.
    """
    # Simple RRF fusion
    scores: Dict[str, float] = {}
    metadata: Dict[str, Dict[str, Any]] = {}
    
    k = 60  # RRF constant

    for rank, doc in enumerate(indexed_results or [], 1):
        doc_id = doc.get("document_id") or doc.get("id", "")
        if not doc_id:
            continue
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        if doc_id not in metadata:
            metadata[doc_id] = {
                "title": doc.get("title", ""),
                "snippet": doc.get("snippet", ""),
                "sources": list(doc.get("sources") or ["indexed"]),
                "from_email": doc.get("from_email") or "",
                "source_type": doc.get("source_type") or "",
                "metadata": dict(doc.get("metadata") or {}) if isinstance(doc.get("metadata"), dict) else {},
            }
            _ingest_hit_meta(metadata[doc_id], doc)
        else:
            src = metadata[doc_id]["sources"]
            for s in doc.get("sources") or ["indexed"]:
                if s not in src:
                    src.append(s)
            _ingest_hit_meta(metadata[doc_id], doc)
    
    for rank, doc in enumerate(lexical_results, 1):
        doc_id = doc.get("document_id") or doc.get("id", "")
        if not doc_id:
            continue
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        if doc_id not in metadata:
            metadata[doc_id] = {
                "title": doc.get("title", ""),
                "snippet": doc.get("snippet", ""),
                "lexical_score": doc.get("score", 0),
                "sources": list(doc.get("sources") or ["lexical"]),
                "from_email": doc.get("from_email") or "",
                "source_type": doc.get("source_type") or "",
                "metadata": dict(doc.get("metadata") or {}) if isinstance(doc.get("metadata"), dict) else {},
            }
            _ingest_hit_meta(metadata[doc_id], doc)
        else:
            src = metadata[doc_id]["sources"]
            for s in doc.get("sources") or ["lexical"]:
                if s not in src:
                    src.append(s)
            if "lexical" not in src and not doc.get("sources"):
                src.append("lexical")
            metadata[doc_id]["lexical_score"] = doc.get("score", 0)
            _ingest_hit_meta(metadata[doc_id], doc)
    
    for rank, doc in enumerate(vector_results, 1):
        doc_id = doc.get("document_id") or doc.get("id", "")
        if not doc_id:
            continue
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        if doc_id not in metadata:
            metadata[doc_id] = {
                "title": doc.get("title", ""),
                "snippet": doc.get("snippet", ""),
                "vector_score": doc.get("score", 0),
                "sources": ["vector"],
                "from_email": doc.get("from_email") or "",
                "source_type": doc.get("source_type") or "",
                "metadata": dict(doc.get("metadata") or {}) if isinstance(doc.get("metadata"), dict) else {},
            }
            _ingest_hit_meta(metadata[doc_id], doc)
        else:
            if "vector" not in metadata[doc_id]["sources"]:
                metadata[doc_id]["sources"].append("vector")
            metadata[doc_id]["vector_score"] = doc.get("score", 0)
            _ingest_hit_meta(metadata[doc_id], doc)
    
    # Sort by fusion score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:size]
    
    items: List[ResultItem] = []
    for doc_id, score in ranked:
        meta_bucket = metadata[doc_id]
        hit_meta = dict(meta_bucket.get("metadata") or {})
        if meta_bucket.get("from_email"):
            hit_meta.setdefault("from_email", meta_bucket["from_email"])
        if meta_bucket.get("source_type"):
            hit_meta.setdefault("source_type", meta_bucket["source_type"])
        items.append(
            ResultItem(
                document_id=doc_id,
                score=score,
                fusion_score=score,
                title=meta_bucket.get("title", ""),
                snippet=meta_bucket.get("snippet", ""),
                sources=meta_bucket.get("sources", []),
                lexical_score=meta_bucket.get("lexical_score"),
                vector_score=meta_bucket.get("vector_score"),
                metadata=hit_meta or None,
            )
        )
    return items


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
    # --- Rule #2, Stage 1: raw query ---
    tracer = _get_rag_tracer()
    tracer.log_raw_query(query)
    # --- Rule #2, Stage 2: query rewriting (not implemented yet) ---
    tracer.log_rewritten_query(None)

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
        lexical_results,
        vector_results,
        size,
        indexed_results=indexed_results,
    )
    return merged, statuses


@router.post("/search/federated", response_model=FederatedSearchResponse)
async def federated_search(
    body: FederatedSearchRequest,
    current_user: Dict[str, Any] = Depends(require_scope("search.read")),
    db_session = Depends(get_tenant_session),
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
    
    admin_denied_ids = await access_override_service.load_denied_ids_for_caller(
        current_user, tenant_id, db_session
    )
    if admin_denied_ids:
        merged = filter_results_with_admin_overrides(
            results=merged,
            admin_denied_ids=admin_denied_ids
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
        "lexical": bool(settings.opensearch_url or settings.lexical_search_url),
        "vector": bool(settings.qdrant_url),
        "graph": bool(settings.neo4j_uri),
    }
    
    return {
        "status": "healthy",
        "backends_configured": backends,
    }
