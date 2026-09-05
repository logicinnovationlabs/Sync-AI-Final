"""
Vector Search API endpoints for Block G.
Provides semantic search with cosine similarity and ACL prefiltering.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.api.deps import get_current_user, require_scope, get_tenant_session
from app.acl.filter import acl_terms_from_jwt, is_fail_closed, filter_results_with_admin_overrides
from app.services.vector.qdrant_store import QdrantVectorStore
from app.services.admin.access_override_service import access_override_service

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response Models
class VectorSearchRequest(BaseModel):
    """Vector search request."""
    query_embedding: List[float] = Field(..., description="Query vector embedding")
    tenant_id: str = Field(..., description="Tenant identifier (must match JWT)")
    user_id: str = Field(..., description="User identifier (ignored for ACL; JWT is source of truth)")
    acl_terms: List[str] = Field(
        default_factory=list,
        description="Ignored. ACL is derived from the JWT, never from the body.",
    )
    top_k: int = Field(10, ge=1, le=100, description="Number of results")
    model_version: Optional[str] = Field(None, description="Filter by embedding model version")
    score_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum similarity score")


class VectorSearchResult(BaseModel):
    """Single vector search result."""
    chunk_id: str
    document_id: str
    score: float
    model_version: str
    chunk_text: str
    metadata: Optional[Dict[str, Any]] = None


class VectorSearchResponse(BaseModel):
    """Vector search response."""
    results: List[VectorSearchResult]
    model_versions_used: List[str]
    took_ms: float


# Dependency to get store
_store_instance = None

def get_vector_store() -> QdrantVectorStore:
    """Get singleton vector store instance."""
    global _store_instance
    if _store_instance is None:
        _store_instance = QdrantVectorStore()
    return _store_instance


async def get_tenant(current_user: Dict[str, Any] = Depends(get_current_user)) -> str:
    """Extract tenant_id from authenticated user."""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")
    return tenant_id


@router.post("/search/vector", response_model=VectorSearchResponse)
async def search_vector(
    request: VectorSearchRequest,
    current_user: Dict[str, Any] = Depends(require_scope("search.read")),
    tenant_id: str = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
    store: QdrantVectorStore = Depends(get_vector_store),
):
    """
    Execute semantic vector search with cosine similarity.
    
    - ACL prefiltering applied before retrieval
    - Empty acl_terms results in empty response (fail-closed)
    - Supports model version isolation
    - Scores from different model versions should not be compared
    
    Requires JWT with 'search.read' scope.
    """
    # Verify tenant binding
    if request.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID mismatch")
    
    # Validate embedding dimensions
    expected_dims = getattr(settings, 'embedding_dimensions', 384)
    if len(request.query_embedding) != expected_dims:
        raise HTTPException(
            status_code=400,
            detail=f"Query embedding must have {expected_dims} dimensions, got {len(request.query_embedding)}"
        )

    acl_terms = acl_terms_from_jwt(current_user)
    
    # Fail-closed if no ACL terms
    if is_fail_closed(acl_terms):
        logger.warning(
            "ACL empty for user=%s tenant=%s — fail-closed",
            current_user.get("sub") or request.user_id,
            request.tenant_id,
        )
        return VectorSearchResponse(results=[], model_versions_used=[], took_ms=0.0)
    
    admin_denied_ids = await access_override_service.load_denied_ids_for_caller(
        current_user, tenant_id, db_session
    )
    
    # Execute search
    started = time.perf_counter()
    try:
        raw = await store.search(
            tenant_id=request.tenant_id,
            query_embedding=request.query_embedding,
            acl_terms=acl_terms,
            top_k=request.top_k,
            model_version=request.model_version,
            score_threshold=request.score_threshold,
        )
    except Exception as exc:
        logger.exception("Vector search failed: %s", exc)
        raise HTTPException(status_code=500, detail="Vector search failed") from exc
    
    took_ms = (time.perf_counter() - started) * 1000.0
    
    if took_ms > 100:
        logger.warning(
            f"Performance outlier: took_ms={took_ms:.2f} tenant={request.tenant_id} top_k={request.top_k}"
        )
    
    # Apply admin deny override filtering (Part 2.3 enforcement)
    if admin_denied_ids:
        original_count = len(raw)
        raw = filter_results_with_admin_overrides(raw, admin_denied_ids)
        filtered_count = original_count - len(raw)
        if filtered_count > 0:
            logger.info(
                f"Admin override filtering: removed {filtered_count} documents from results"
            )
    
    # Build response
    results = [
        VectorSearchResult(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            score=r["score"],
            model_version=r["model_version"],
            chunk_text=r.get("chunk_text", ""),
            metadata=r.get("metadata"),
        )
        for r in raw
    ]
    
    model_versions_used = sorted(set(r.model_version for r in results if r.model_version))
    
    return VectorSearchResponse(
        results=results,
        model_versions_used=model_versions_used,
        took_ms=took_ms,
    )


@router.post("/search/vector/ingest", status_code=202)
async def ingest_vectors(
    chunks: List[Dict[str, Any]],
    current_user: Dict[str, Any] = Depends(require_scope("index.write")),
    tenant_id: str = Depends(get_tenant),
    store: QdrantVectorStore = Depends(get_vector_store),
):
    """
    Manually ingest chunk vectors.
    
    Useful for bulk re-indexing or initial population.
    Requires JWT with 'index.write' scope.
    """
    # Validate chunks
    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks provided")
    
    # Upsert batch
    try:
        count = await store.upsert_batch(tenant_id=tenant_id, chunks=chunks)
    except Exception as exc:
        logger.exception("Vector ingestion failed: %s", exc)
        raise HTTPException(status_code=500, detail="Vector ingestion failed") from exc
    
    logger.info(f"Ingested {count} vectors for tenant {tenant_id}")
    
    return {
        "message": f"Ingested {count} vectors",
        "tenant_id": tenant_id,
    }
