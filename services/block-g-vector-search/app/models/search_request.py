"""Search request/response models for POST /api/v1/search/vector."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, AliasChoices


class SearchRequest(BaseModel):
    """Query-time ANN search request from Block J / callers."""

    tenant_id: str = Field(..., description="Tenant scope (must match JWT)")
    principal_id: str = Field(..., description="Requesting principal")
    acl_terms: List[str] = Field(
        ...,
        description="Caller principal/group IDs used for ACL prefilter",
        validation_alias=AliasChoices("acl_terms", "acl_filter_terms"),
    )
    query_embedding: List[float] = Field(..., description="Query vector")
    model_version: Optional[str] = Field(
        None,
        description="Restrict results to this embedding model version",
    )
    top_k: int = Field(100, ge=1, le=500, description="Max candidates")
    score_threshold: Optional[float] = Field(
        None,
        description="Minimum similarity score (inclusive)",
    )

    model_config = {"populate_by_name": True}


class SearchResult(BaseModel):
    """Single ranked candidate chunk."""

    chunk_id: str
    document_id: str
    score: float
    model_version: str
    chunk_text: str
    metadata: Optional[Dict[str, Any]] = None


class SearchResponse(BaseModel):
    """Ranked ANN results for Block J."""

    results: List[SearchResult]
    model_versions_used: List[str]