"""
Lexical Search API endpoints for Block F.
Provides full-text search with BM25 ranking and ACL prefiltering.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.api.deps import get_current_user, require_scope, get_tenant_session
from app.acl.filter import acl_terms_from_jwt, is_fail_closed, filter_results_with_admin_overrides
from app.services.lexical.opensearch_store import OpenSearchLexicalStore
from app.services.admin.access_override_service import access_override_service

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response Models
class SearchFilters(BaseModel):
    """Optional metadata filters for search."""
    repository: Optional[str] = None
    source: Optional[str] = None
    language: Optional[str] = None
    object_type: Optional[str] = None


class SearchRequest(BaseModel):
    """Lexical search request."""
    query: str = Field(..., description="Search query string")
    tenant_id: str = Field(..., description="Tenant identifier (must match JWT)")
    user_id: str = Field(..., description="User identifier (ignored for ACL; JWT is source of truth)")
    acl_terms: List[str] = Field(
        default_factory=list,
        description="Ignored. ACL is derived from the JWT, never from the body.",
    )
    filters: Optional[SearchFilters] = None
    facets: Optional[List[str]] = Field(None, description="Facet fields to aggregate")
    from_: int = Field(0, ge=0, alias="from", description="Pagination offset")
    size: int = Field(20, ge=1, le=100, description="Number of results")


class SearchResult(BaseModel):
    """Single search result."""
    document_id: str
    score: float
    title: str
    snippet: str
    metadata: Optional[Dict[str, Any]] = None


class FacetBucket(BaseModel):
    """Facet bucket with count."""
    value: str
    count: int


class SearchResponse(BaseModel):
    """Lexical search response."""
    results: List[SearchResult]
    facets: Dict[str, List[FacetBucket]]
    total: int
    took_ms: float


# Dependency to get store
_store_instance = None

def get_lexical_store() -> OpenSearchLexicalStore:
    """Get singleton lexical store instance."""
    global _store_instance
    if _store_instance is None:
        _store_instance = OpenSearchLexicalStore()
    return _store_instance


async def get_tenant(current_user: Dict[str, Any] = Depends(get_current_user)) -> str:
    """Extract tenant_id from authenticated user."""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")
    return tenant_id


@router.post("/search/lexical", response_model=SearchResponse)
async def search_lexical(
    request: SearchRequest,
    current_user: Dict[str, Any] = Depends(require_scope("search.read")),
    tenant_id: str = Depends(get_tenant),
    store: OpenSearchLexicalStore = Depends(get_lexical_store),
    db_session = Depends(get_tenant_session),
):
    """
    Execute full-text lexical search with BM25 ranking.
    
    - ACL prefiltering applied before retrieval
    - Empty acl_terms results in empty response (fail-closed)
    - Supports faceted search and metadata filtering
    
    Requires JWT with 'search.read' scope.
    """
    # Verify tenant binding
    if request.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID mismatch")

    acl_terms = acl_terms_from_jwt(current_user)
    
    # Fail-closed if no ACL terms
    if is_fail_closed(acl_terms):
        logger.warning(
            "ACL empty for user=%s tenant=%s — fail-closed",
            current_user.get("sub") or request.user_id,
            request.tenant_id,
        )
        return SearchResponse(results=[], facets={}, total=0, took_ms=0.0)

    admin_denied_ids = await access_override_service.load_denied_ids_for_caller(
        current_user, tenant_id, db_session
    )
    
    # Execute search
    started = time.perf_counter()
    try:
        filters_dict = request.filters.model_dump(exclude_none=True) if request.filters else None
        
        raw = await store.search(
            tenant_id=request.tenant_id,
            query=request.query,
            acl_terms=acl_terms,
            filters=filters_dict,
            facets=request.facets,
            from_=request.from_,
            size=request.size,
        )

        if admin_denied_ids:
            raw_results = raw.get("results", [])
            filtered_results = filter_results_with_admin_overrides(
                results=raw_results,
                admin_denied_ids=admin_denied_ids
            )
            raw["results"] = filtered_results
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Lexical search failed: %s", exc)
        raise HTTPException(status_code=500, detail="Lexical search failed") from exc
    
    took_ms = (time.perf_counter() - started) * 1000.0
    
    if took_ms > 200:
        logger.warning(
            f"Performance outlier: took_ms={took_ms:.2f} tenant={request.tenant_id} query_len={len(request.query)}"
        )
    
    # Build response
    results = [
        SearchResult(
            document_id=r["document_id"],
            score=r["score"],
            title=r.get("title", ""),
            snippet=r.get("snippet", ""),
            metadata=r.get("metadata"),
        )
        for r in raw.get("results", [])
    ]
    
    facets = {
        field: [FacetBucket(value=b["value"], count=b["count"]) for b in buckets]
        for field, buckets in raw.get("facets", {}).items()
    }
    
    return SearchResponse(
        results=results,
        facets=facets,
        total=raw.get("total", 0),
        took_ms=took_ms,
    )


@router.post("/index", status_code=202)
async def trigger_index(
    document_ids: List[str],
    current_user: Dict[str, Any] = Depends(require_scope("index.write")),
    tenant_id: str = Depends(get_tenant),
):
    """
    Manually trigger indexing for specific documents.
    
    Useful for re-indexing after ACL changes or document updates.
    Requires JWT with 'index.write' scope.
    """
    # In production, this would enqueue a Celery task
    logger.info(f"Triggered indexing for {len(document_ids)} documents in tenant {tenant_id}")
    
    return {
        "message": f"Indexing queued for {len(document_ids)} documents",
        "document_ids": document_ids,
    }
