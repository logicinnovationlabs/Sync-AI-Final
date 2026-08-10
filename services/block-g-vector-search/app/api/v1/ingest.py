"""POST /api/v1/ingest — accept chunk embeddings from Block E."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Union

from fastapi import APIRouter, Depends, HTTPException

from app.auth import assert_tenant_binding, get_current_user
from app.models.chunk import (
    ChunkIngestBatchRequest,
    ChunkIngestRequest,
    ChunkIngestResponse,
)
from app.services.acl_filter import normalize_acl_terms
from app.services.factory import get_vector_store
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ingest"])


def get_store() -> VectorStore:
    return get_vector_store()


async def _upsert_one(store: VectorStore, chunk: ChunkIngestRequest) -> str:
    if not chunk.embedding:
        raise HTTPException(
            status_code=400,
            detail=f"empty embedding for {chunk.chunk_id}",
        )
    await store.upsert_chunk(
        tenant_id=chunk.tenant_id,
        chunk_id=chunk.chunk_id,
        embedding=chunk.embedding,
        metadata={
            "document_id": chunk.document_id,
            "chunk_text": chunk.chunk_text,
            "metadata": chunk.metadata or {},
        },
        acl_terms=normalize_acl_terms(chunk.acl_filter_terms),
        model_version=chunk.model_version,
    )
    return chunk.chunk_id


@router.post("/ingest", response_model=ChunkIngestResponse)
async def ingest_chunks(
    body: Union[ChunkIngestRequest, ChunkIngestBatchRequest, Dict[str, Any]],
    current_user: Dict[str, Any] = Depends(get_current_user),
    store: VectorStore = Depends(get_store),
) -> ChunkIngestResponse:
    """
    Upsert one chunk or a batch.

    Accepts either a single ChunkIngestRequest, {"chunks": [...]}, or a raw
    ingest.chunks.v1-shaped dict.
    """
    token_tenant = str(current_user.get("tenant_id", ""))

    chunks: List[ChunkIngestRequest]
    if isinstance(body, ChunkIngestBatchRequest):
        chunks = body.chunks
    elif isinstance(body, ChunkIngestRequest):
        chunks = [body]
    elif isinstance(body, dict) and "chunks" in body:
        chunks = [ChunkIngestRequest(**c) for c in body["chunks"]]
    elif isinstance(body, dict):
        chunks = [ChunkIngestRequest(**body)]
    else:
        raise HTTPException(status_code=400, detail="Invalid ingest payload")

    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks to ingest")

    tenant_id = chunks[0].tenant_id
    for c in chunks:
        if c.tenant_id != tenant_id:
            raise HTTPException(status_code=400, detail="Mixed tenant_id in batch")
        assert_tenant_binding(c.tenant_id, token_tenant)

    upserted_ids: List[str] = []
    for chunk in chunks:
        cid = await _upsert_one(store, chunk)
        upserted_ids.append(cid)

    logger.info("Ingested %d chunks for tenant %s", len(upserted_ids), tenant_id)
    return ChunkIngestResponse(
        upserted=len(upserted_ids),
        tenant_id=tenant_id,
        chunk_ids=upserted_ids,
    )