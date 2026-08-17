"""Block J: Federated Search Models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


from app.acl.filter import is_fail_closed


class UserContext(BaseModel):
    """Auth context from JWT."""

    tenant_id: str
    principal_id: str
    groups: List[str] = Field(default_factory=list)
    scopes: List[str] = Field(default_factory=list)

    def build_acl_terms(self) -> List[str]:
        """Build ACL terms for filtering."""
        terms = []
        seen = set()
        for t in [self.principal_id, *self.groups]:
            if t and t not in seen:
                seen.add(t)
                terms.append(t)
        if is_fail_closed(terms):
            return []
        return terms


class SearchFilters(BaseModel):
    """Optional structured filters."""

    object_type: Optional[List[str]] = None
    source: Optional[List[str]] = None
    repository: Optional[List[str]] = None
    tags: Optional[List[str]] = None


class FederatedSearchRequest(BaseModel):
    """Federated search request."""

    query: str = Field(..., min_length=1)
    tenant_id: Optional[str] = None
    filters: Optional[SearchFilters] = None
    from_: int = Field(0, ge=0, alias="from")
    size: int = Field(20, ge=1, le=100)
    enable_vector: bool = Field(True)
    enable_lexical: bool = Field(True)
    enable_graph: bool = Field(False)

    model_config = {"populate_by_name": True}


class Citation(BaseModel):
    """Source citation."""

    document_id: str
    title: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None


class ResultItem(BaseModel):
    """Federated search result."""

    document_id: str
    score: float
    title: str = ""
    snippet: str = ""
    sources: List[str] = Field(default_factory=list)
    lexical_score: Optional[float] = None
    vector_score: Optional[float] = None
    graph_boost: Optional[float] = None
    fusion_score: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    citations: List[Citation] = Field(default_factory=list)


class BackendStatus(BaseModel):
    """Per-backend status."""

    name: str
    ok: bool
    latency_ms: float = 0.0
    error: Optional[str] = None
    hit_count: int = 0


class FederatedSearchResponse(BaseModel):
    """Federated search response."""

    results: List[ResultItem]
    total: int = 0
    took_ms: float = 0.0
    degraded: bool = False
    backends: List[BackendStatus] = Field(default_factory=list)
    query: Optional[str] = None
