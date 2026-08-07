"""Chunk ingest models (Block E -> Block G)."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, AliasChoices


class ChunkIngestRequest(BaseModel):
    """Payload for POST /api/v1/ingest (ingest.chunks.v1 shape)."""

    tenant_id: str = Field(..., description="Tenant owning this chunk")
    chunk_id: str = Field(..., description="Stable chunk identifier")
    document_id: str = Field(..., description="Parent document identifier")
    embedding: List[float] = Field(..., description="Embedding vector")
    model_version: str = Field(..., description="Embedding model version tag")
    chunk_text: str = Field(..., description="Chunk text content")
    acl_filter_terms: List[str] = Field(
        default_factory=list,
        description="Principal/group IDs that may read this chunk",
        validation_alias=AliasChoices("acl_filter_terms", "acl_terms"),
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional opaque metadata",
    )

    model_config = {"populate_by_name": True}


class ChunkIngestBatchRequest(BaseModel):
    """Batch ingest of multiple chunks."""

    chunks: List[ChunkIngestRequest]


class ChunkIngestResponse(BaseModel):
    """Response after upserting one or more chunks."""

    upserted: int
    tenant_id: str
    chunk_ids: List[str]