"""Core document reader logic: fetch, ACL gate, redact, structure preserve."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import HTTPException

from app.services.document_reader.acl_checker import ACLChecker, check_acl
from app.services.document_reader.store import DocumentStore

logger = logging.getLogger(__name__)

# Fields that may be redacted for non-owners when marked hidden
_SENSITIVE_META_KEYS = frozenset(
    {"internal_notes", "hidden_annotation", "salary", "ssn", "secret_field"}
)


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def redact_fields(metadata: Dict[str, Any], principal_id: str) -> Dict[str, Any]:
    """
    Intra-tenant redaction based on visibility_mode / hidden_fields.

    Owners see all fields. Non-owners lose keys listed in hidden_fields
    (plus known sensitive keys when visibility_mode == ''redacted'').
    """
    visible = dict(metadata)
    owner = str(visible.get("owner_principal_id") or "")
    if owner and owner == principal_id:
        return visible

    hidden = set(visible.get("hidden_fields") or [])
    mode = str(visible.get("visibility_mode") or "acl").lower()
    if mode == "redacted":
        hidden |= _SENSITIVE_META_KEYS

    for key in list(hidden):
        visible.pop(key, None)

    return visible


async def read_document(
    store: DocumentStore,
    acl_checker: ACLChecker,
    tenant_id: str,
    doc_id: str,
    principal_id: str,
    stream_threshold_bytes: int,
) -> tuple[Dict[str, Any], Optional[bytes], Optional[AsyncGenerator[bytes, None]]]:
    """
    K1: ACL re-check (no cache)
    K2: Streaming for large docs
    K3: Structure preservation
    """
    # K1: Re-check ACL on every access
    allowed = await check_acl(acl_checker, tenant_id, principal_id, doc_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="Access denied")

    # Fetch metadata
    meta = await store.get_metadata(tenant_id, doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Document not found")

    # Redact hidden fields
    visible_meta = redact_fields(meta, principal_id)

    # K2: Stream if body_size > threshold
    body_size = int(visible_meta.get("body_size") or 0)
    object_key = str(visible_meta.get("object_key") or "")

    if body_size > stream_threshold_bytes:
        # Return metadata + stream generator
        stream = store.get_body_stream(object_key)
        return visible_meta, None, stream
    else:
        # Return metadata + full body
        body = await store.get_body(object_key) if object_key else b""
        return visible_meta, body, None


def build_document_payload(
    metadata: Dict[str, Any],
    body: Optional[bytes],
    structured: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """K3: Preserve structure + metadata + body."""
    payload = dict(metadata)
    if body is not None:
        try:
            payload["body"] = body.decode("utf-8")
        except UnicodeDecodeError:
            payload["body_base64"] = body.hex()
    if structured:
        payload["structured_metadata"] = structured
    return payload


async def stream_document_json(
    metadata: Dict[str, Any],
    stream: AsyncGenerator[bytes, None],
    structured: Optional[Dict[str, Any]],
) -> AsyncGenerator[str, None]:
    """K2: Stream large documents as JSON chunks."""
    # Start JSON
    meta_copy = dict(metadata)
    if structured:
        meta_copy["structured_metadata"] = structured

    yield json.dumps({"metadata": meta_copy, "body_chunks": []}) + "\n"

    # Stream body chunks
    async for chunk in stream:
        try:
            chunk_str = chunk.decode("utf-8")
        except UnicodeDecodeError:
            chunk_str = chunk.hex()
        yield json.dumps({"chunk": chunk_str}) + "\n"
