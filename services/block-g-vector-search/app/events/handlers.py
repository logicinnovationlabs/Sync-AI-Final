"""Event bus handlers for ingest.chunks.v1 (optional Kafka/Redpanda path)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.models.chunk import ChunkIngestRequest
from app.services.acl_filter import normalize_acl_terms
from app.services.factory import get_vector_store

logger = logging.getLogger(__name__)


async def handle_ingest_chunks_event(payload: Dict[str, Any]) -> None:
    """
    Consume a single ingest.chunks.v1 message and upsert into the vector store.

    Expected payload fields match ChunkIngestRequest / Block E emit shape.
    """
    chunk = ChunkIngestRequest(**payload)
    store = get_vector_store()
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
    logger.info(
        "Event ingest upserted chunk_id=%s tenant=%s model=%s",
        chunk.chunk_id,
        chunk.tenant_id,
        chunk.model_version,
    )


def parse_event_bytes(raw: bytes) -> Optional[Dict[str, Any]]:
    """Parse UTF-8 JSON event bytes; return None on failure."""
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse ingest event: %s", exc)
        return None
