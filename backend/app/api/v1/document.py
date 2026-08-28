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
from app.services.document_reader.store import (
    InMemoryDocumentStore,
    get_shared_document_store,
)

logger = logging.getLogger(__name__)

# Same in-process store the indexer writes. Celery still cannot share this
# memory — GET falls back to the Qdrant `documents` collection below.
store = get_shared_document_store()
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


async def get_tenant_id(current_user: Dict[str, Any] = Depends(get_current_user)) -> str:
    """Extract tenant_id string from authenticated user claims."""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")
    return str(tenant_id)


def _payload_body(payload: Dict[str, Any]) -> str:
    return str(
        payload.get("content")
        or payload.get("body")
        or payload.get("body_text")
        or payload.get("snippet")
        or ""
    )


async def _load_indexed_document(
    tenant_id: str, doc_id: str
) -> tuple[str, Dict[str, Any]] | None:
    """Read the document Celery actually indexed (shared Qdrant collection)."""
    try:
        from app.storage.qdrant_client import qdrant_client

        payload = await qdrant_client.get_document_payload(tenant_id, doc_id)
        resolved_id = doc_id
        if payload is None:
            from app.services.vector.qdrant_store import QdrantVectorStore

            parent = QdrantVectorStore().find_parent_document_id(tenant_id, doc_id)
            if parent and parent != doc_id:
                payload = await qdrant_client.get_document_payload(tenant_id, parent)
                resolved_id = parent
        if payload is None:
            return None
        return resolved_id, payload
    except Exception:
        logger.warning(
            "indexed document lookup failed id=%s tenant=%s",
            doc_id,
            tenant_id,
            exc_info=True,
        )
        return None


async def _audit_document_acl(
    tenant_id: str, principal_id: str, doc_id: str, allowed: bool
) -> None:
    """Best-effort audit of open-document allow/deny. Never fail the read."""
    action = "document.acl_allow" if allowed else "document.acl_deny"
    logger.info(
        "%s tenant_id=%s principal_id=%s document_id=%s",
        action,
        tenant_id,
        principal_id,
        doc_id,
    )
    try:
        from uuid import UUID

        from app.core.exceptions import TenantNotFoundError
        from app.services.admin.audit_logger import write_audit_log
        from app.services.tenant_resolver import tenant_resolver
        from app.storage.tenant_db import tenant_db_manager

        tenant = UUID(str(tenant_id))
        actor = UUID(str(principal_id))
        routing = await tenant_resolver.resolve(str(tenant_id))
        factory = tenant_db_manager.get_session_factory(
            routing.db_host,
            routing.db_name,
            routing.db_user,
            routing.db_password,
            str(routing.tenant_id),
        )
        session = factory()
        try:
            await write_audit_log(
                session,
                tenant_id=tenant,
                actor_id=actor,
                action_type=action,
                target={"document_id": doc_id, "allowed": allowed},
            )
            await session.commit()
        finally:
            await session.close()
    except (TenantNotFoundError, TypeError, ValueError):
        return
    except Exception:
        logger.exception("document ACL audit write failed")


@router.get("/document/{doc_id}")
async def get_document(
    doc_id: str,
    tenant_id: str = Depends(get_tenant_id),
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

    async def _decide(doc_key: str) -> bool:
        allowed = await acl_checker.is_allowed(tenant_id, principal_id, doc_key)
        await _audit_document_acl(
            tenant_id, principal_id, doc_key, allowed
        )
        return allowed

    metadata = await store.get_metadata(tenant_id, doc_id)
    if not metadata and isinstance(store, InMemoryDocumentStore):
        indexed = await _load_indexed_document(tenant_id, doc_id)
        if indexed:
            resolved_id, payload = indexed
            allowed = await _decide(resolved_id)
            if not allowed:
                raise HTTPException(status_code=403, detail="Forbidden")
            body = _payload_body(payload)
            visible_metadata = redact_fields(
                {
                    "document_id": resolved_id,
                    "tenant_id": tenant_id,
                    "title": payload.get("title") or "",
                    "source_type": payload.get("source_type"),
                    "url": payload.get("url"),
                    "created_at": payload.get("created_at"),
                    "updated_at": payload.get("updated_at"),
                    "owner_principal_id": payload.get("owner_principal_id") or "",
                },
                principal_id,
            )
            structured = payload.get("structured_metadata")
            return build_document_payload(
                doc_id=resolved_id,
                tenant_id=tenant_id,
                visible_metadata=visible_metadata,
                body=body,
                structured_data=structured if isinstance(structured, dict) else {},
            )

    if not metadata:
        raise HTTPException(status_code=404, detail="Document not found")

    # K1: ACL re-check on every request — no caching
    allowed = await _decide(doc_id)
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
