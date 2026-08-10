"""Pydantic schemas for Block J search API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, AliasChoices


class UserContext(BaseModel):
    """Auth context extracted from Block A JWT."""

    tenant_id: str
    principal_id: str
    groups: List[str] = Field(default_factory=list)
    scopes: List[str] = Field(default_factory=list)
    acl_terms: List[str] = Field(
        default_factory=list,
        description="Principal + group terms used for backend ACL prefilters",
    )

    def build_acl_terms(self) -> List[str]:
        """Union of explicit acl_terms, principal, and groups (deduped)."""
        terms: List[str] = []
        seen = set()
        for t in [*self.acl_terms, self.principal_id, *self.groups]:
            if t and t not in seen:
                seen.add(t)
                terms.append(t)
        return terms


class SearchFilters(BaseModel):
    """Optional structured filters passed through to lexical search."""

    object_type: Optional[List[str]] = None
    source: Optional[List[str]] = None
    repository: Optional[List[str]] = None
    owner: Optional[List[str]] = None
    language: Optional[List[str]] = None
    tags: Optional[List[str]] = None


class SearchRequest(BaseModel):
    """POST /api/v1/search body."""

    query: str = Field(..., min_length=1, description="User search query")
    tenant_id: Optional[str] = Field(
        default=None,
        description="Optional; must match JWT when isolation is enforced",
    )
    filters: Optional[SearchFilters] = None
    facets: Optional[List[str]] = Field(
        default=None,
        description="Facet fields requested from lexical backend",
    )
    from_: int = Field(0, ge=0, alias="from", description="Result offset")
    size: int = Field(20, ge=1, le=100, description="Page size")
    query_embedding: Optional[List[float]] = Field(
        default=None,
        description="Optional precomputed embedding; otherwise generated",
    )
    debug: bool = Field(False, description="Include backend diagnostics")

    model_config = {"populate_by_name": True}


class Citation(BaseModel):
    """Source citation for a result."""

    document_id: str
    title: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None


class ResultItem(BaseModel):
    """Single ranked, permission-safe search hit."""

    document_id: str
    score: float
    title: str = ""
    snippet: str = ""
    sources: List[str] = Field(
        default_factory=list,
        description="Backends that contributed: lexical|vector|graph",
    )
    lexical_score: Optional[float] = None
    vector_score: Optional[float] = None
    graph_boost: Optional[float] = None
    fusion_score: Optional[float] = None
    rerank_score: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    citations: List[Citation] = Field(default_factory=list)


class FacetBucket(BaseModel):
    value: str
    count: int


class BackendStatus(BaseModel):
    """Per-backend health contribution for a single request."""

    name: str
    ok: bool
    latency_ms: float = 0.0
    error: Optional[str] = None
    hit_count: int = 0


class SearchResponse(BaseModel):
    """Final federated search response."""

    results: List[ResultItem]
    facets: Dict[str, List[FacetBucket]] = Field(default_factory=dict)
    total: int = 0
    took_ms: float = 0.0
    degraded: bool = False
    backends: List[BackendStatus] = Field(default_factory=list)
    query: Optional[str] = None


class Candidate(BaseModel):
    """Internal merged candidate before final ranking/pagination."""

    document_id: str
    title: str = ""
    snippet: str = ""
    lexical_score: float = 0.0
    vector_score: float = 0.0
    graph_boost: float = 0.0
    fusion_score: float = 0.0
    rerank_score: Optional[float] = None
    sources: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    chunk_text: Optional[str] = None

    def text_for_rerank(self) -> str:
        """Best available text for cross-encoder input."""
        if self.snippet:
            return f"{self.title} {self.snippet}".strip()
        if self.chunk_text:
            return f"{self.title} {self.chunk_text}".strip()
        return self.title or self.document_id
