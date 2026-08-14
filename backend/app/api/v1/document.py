"""Block K: Document Reader API endpoint.

GET /api/v1/document/{doc_id} - Full document retrieval with ACL re-check.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import get_current_user, get_tenant
from app.core.config import settings
from app.services.document_reader.acl_checker import create_acl_checker
from app.services.document_reader.reader import (
    build_document_payload,
    redact_fields,
    stream_document_json,
)
from app.services.document_reader.store import create_document_store

logger = logging.getLogger(__name__)

# Initialize Block K components
store = create_document_store(settings)
acl_checker = create_acl_checker(settings)

# Router for document endpoints
router = APIRouter(prefix="", tags=["document-reader"])


@router.on_event("startup")
async def startup():
    """Initialize document store connection."""
    await store.connect()
    logger.info(
        "Block K Document Reader initialized (storage=%s acl=%s threshold=%s)",
        settings.storage_backend,
        settings.acl_backend,
        settings.stream_threshold_bytes,
    )


@router.on_event("shutdown")
async def shutdown():
    """Close document store connection."""
    await store.close()
    logger.info("Block K Document Reader shut down")


@router.get("/document/{doc_id}")
async def get_document(
    doc_id: str,
    tenant_id: str = Depends(get_tenant),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    GET full document by ID with ACL re-check and optional streaming.
    
    Block K Signoff Criteria:
    - K1: ACL re-check on every request (no caching)
    - K2: Stream large documents (>10MB) with bounded memory
    - K3: Structure preservation (headings, tables, code blocks)
    """
    principal_id = str(
        current_user.get("principal_id")
        or current_user.get("sub")
        or current_user.get("user_id")
        or ""
    )
    if not principal_id:
        raise HTTPException(status_code=401, detail="principal_id missing from token")

    metadata = await store.get_metadata(tenant_id, doc_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Document not found")

    # K1: ACL re-check on every request — no caching
    allowed = await acl_checker.is_allowed(tenant_id, principal_id, doc_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="Forbidden")

    object_key = metadata.get("object_key")
    if not object_key:
        raise HTTPException(status_code=500, detail="Document object missing")

    visible_metadata = redact_fields(metadata, principal_id)
    structured_data = await store.get_structured_metadata(tenant_id, doc_id)
    body_size = int(metadata.get("body_size") or 0)

    if body_size > settings.stream_threshold_bytes:
        # K2: stream large documents with bounded memory
        return StreamingResponse(
            stream_document_json(
                store,
                object_key,
                doc_id,
                tenant_id,
                visible_metadata,
                structured_data,
            ),
            media_type="application/json",
            headers={"X-Document-Streaming": "1", "X-Document-Size": str(body_size)},
        )

    try:
        raw = await store.get_body(object_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document body not found") from exc

    body = raw.decode("utf-8", errors="replace")
    return build_document_payload(
        doc_id=doc_id,
        tenant_id=tenant_id,
        visible_metadata=visible_metadata,
        body=body,
        structured_data=structured_data,
    )
