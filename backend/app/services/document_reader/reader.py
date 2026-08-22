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
    (plus known sensitive keys when visibility_mode == 'redacted').
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
    # K1: Re-check live acl_entries on every access (deny-wins, fail-closed).
    # No request-path cache. Checker is Mock/HTTP/Postgres; production uses Postgres.
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
    *,
    doc_id: str,
    tenant_id: str,
    visible_metadata: Dict[str, Any],
    body: str,
    structured_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """K3: Preserve structure + metadata + body as a single JSON object."""
    payload = dict(visible_metadata)
    payload["document_id"] = doc_id
    payload["tenant_id"] = tenant_id
    payload["body"] = body
    payload["structured_metadata"] = structured_data or {}
    return payload


async def stream_document_json(
    store: DocumentStore,
    object_key: str,
    doc_id: str,
    tenant_id: str,
    visible_metadata: Dict[str, Any],
    structured_data: Optional[Dict[str, Any]],
) -> AsyncGenerator[bytes, None]:
    """K2: Stream a complete JSON document without holding the full body.

    Chunks concatenate to one JSON object so HTTP clients can ``.json()`` it,
    while the generator itself retains only the current chunk.
    """
    header = dict(visible_metadata)
    header["document_id"] = doc_id
    header["tenant_id"] = tenant_id
    header["structured_metadata"] = structured_data or {}
    header["body"] = ""
    prefix = json.dumps(header, ensure_ascii=False)
    yield prefix[:-2].encode("utf-8")
    async for raw in store.get_body_stream(object_key):
        text = raw.decode("utf-8", errors="replace")
        yield json.dumps(text, ensure_ascii=False)[1:-1].encode("utf-8")
    yield b'"}'
