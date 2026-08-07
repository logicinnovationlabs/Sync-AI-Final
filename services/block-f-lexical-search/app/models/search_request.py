"""Search request/response models for POST /search/lexical."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, AliasChoices


class SearchFilters(BaseModel):
    """Structured filters applied in filter context (alongside ACL)."""

    object_type: Optional[List[str]] = None
    source: Optional[List[str]] = None
    repository: Optional[List[str]] = None
    owner: Optional[List[str]] = None
    language: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    file_path_prefix: Optional[str] = None
    extension: Optional[str] = None


class SearchRequest(BaseModel):
    """Lexical search request from Block J / callers."""

    query: str = Field(..., description="Keyword query (required)")
    tenant_id: str = Field(..., description="Tenant scope (must match JWT)")
    user_id: str = Field(
        ...,
        description="Requesting principal",
        validation_alias=AliasChoices("user_id", "principal_id"),
    )
    acl_terms: List[str] = Field(
        ...,
        description="Caller principal/group IDs used for ACL prefilter",
        validation_alias=AliasChoices("acl_terms", "acl_filter_terms"),
    )
    filters: Optional[SearchFilters] = None
    facets: Optional[List[str]] = Field(
        default=None,
        description="Facet fields: object_type, source, repository, owner, language, tags",
    )
    from_: int = Field(0, ge=0, alias="from", description="Offset (prefer search_after in prod)")
    size: int = Field(20, ge=1, le=100, description="Page size")

    model_config = {"populate_by_name": True}


class SearchResult(BaseModel):
    """Single ranked lexical hit."""

    document_id: str
    score: float
    title: str
    snippet: str
    metadata: Optional[Dict[str, Any]] = None


class FacetBucket(BaseModel):
    value: str
    count: int


class SearchResponse(BaseModel):
    """Ranked lexical results with optional facets."""

    results: List[SearchResult]
    facets: Dict[str, List[FacetBucket]] = Field(default_factory=dict)
    total: int = 0
    took_ms: float = 0.0
