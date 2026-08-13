"""Request/response schemas for Block H graph APIs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TraverseRequest(BaseModel):
    """POST /graph/traverse body."""

    start_node_id: str = Field(..., description="source_id of the start node")
    relationship_types: Optional[List[str]] = Field(
        default=None,
        description="Optional filter; all relationship types if omitted",
    )
    depth: int = Field(default=2, ge=0, le=2, description="Max depth (signoff: ≤ 2)")
    tenant_id: Optional[str] = Field(
        default=None,
        description="Optional explicit tenant; must match JWT when isolation enforced",
    )


class GraphNode(BaseModel):
    source_id: str
    labels: List[str] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphRelationship(BaseModel):
    type: str
    source_id: str
    target_id: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class TraverseResponse(BaseModel):
    nodes: List[GraphNode]
    relationships: List[GraphRelationship]
    start_node_id: str
    depth: int


class PersonResult(BaseModel):
    id: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    title: Optional[str] = None
    department: Optional[str] = None
    team: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)


class PeopleSearchResponse(BaseModel):
    results: List[PersonResult]
    query: str
    count: int


class RelatedResponse(BaseModel):
    node_id: str
    related: List[Dict[str, Any]]
    count: int


class MergePersonsRequest(BaseModel):
    primary_id: str = Field(..., description="Person source_id to keep")
    secondary_id: str = Field(..., description="Person source_id to merge away")
    tenant_id: Optional[str] = None


class MergePersonsResponse(BaseModel):
    primary_id: str
    secondary_id: str
    edges_redirected: int
    secondary_deleted: bool


class SplitPersonsRequest(BaseModel):
    """Restore a prior merge using a merge snapshot id (optional for signoff)."""

    primary_id: str
    secondary_id: str
    tenant_id: Optional[str] = None
    snapshot: Optional[Dict[str, Any]] = None
