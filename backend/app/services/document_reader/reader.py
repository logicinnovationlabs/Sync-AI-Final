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
    doc_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    visible_metadata: Optional[Dict[str, Any]] = None,
    body: Optional[str | bytes] = None,
    structured_data: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    structured: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """K3: Preserve structure + metadata + body."""
    payload = dict(visible_metadata or metadata or {})
    if doc_id:
        payload["document_id"] = doc_id
    if tenant_id:
        payload["tenant_id"] = tenant_id

    if body is not None:
        if isinstance(body, bytes):
            try:
                payload["body"] = body.decode("utf-8")
            except UnicodeDecodeError:
                payload["body_base64"] = body.hex()
        else:
            payload["body"] = str(body)

    struct = structured_data if structured_data is not None else structured
    if struct is not None:
        payload["structured_metadata"] = struct
    return payload


async def stream_document_json(
    store_or_meta: Any,
    object_key_or_stream: Any = None,
    doc_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    visible_metadata: Optional[Dict[str, Any]] = None,
    structured_data: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[str, None]:
    """
    K2: Stream large documents as valid JSON with bounded memory (<5MB).
    Yields progressive JSON text: {"document_id": "...", ..., "body": "AAAA..."}
    """
    if hasattr(store_or_meta, "get_body_stream"):
        store = store_or_meta
        object_key = object_key_or_stream
        meta = dict(visible_metadata or {})
        if doc_id:
            meta["document_id"] = doc_id
        if tenant_id:
            meta["tenant_id"] = tenant_id
        if structured_data is not None:
            meta["structured_metadata"] = structured_data

        # Serialize metadata fields
        meta_items = [f"{json.dumps(k)}: {json.dumps(v)}" for k, v in meta.items()]
        prefix = "{" + ", ".join(meta_items) + (", " if meta_items else "") + '"body": "'
        yield prefix

        async for chunk_bytes in store.get_body_stream(object_key):
            try:
                chunk_str = chunk_bytes.decode("utf-8")
            except UnicodeDecodeError:
                chunk_str = chunk_bytes.hex()
            # Escape chunk characters for JSON string body
            escaped_chunk = json.dumps(chunk_str)[1:-1]
            yield escaped_chunk

        yield '"}'
    else:
        meta = dict(store_or_meta or {})
        stream = object_key_or_stream
        if doc_id and isinstance(doc_id, dict):
            meta["structured_metadata"] = doc_id

        meta_items = [f"{json.dumps(k)}: {json.dumps(v)}" for k, v in meta.items()]
        prefix = "{" + ", ".join(meta_items) + (", " if meta_items else "") + '"body": "'
        yield prefix

        if stream:
            async for chunk_bytes in stream:
                if isinstance(chunk_bytes, bytes):
                    chunk_str = chunk_bytes.decode("utf-8", errors="replace")
                else:
                    chunk_str = str(chunk_bytes)
                escaped_chunk = json.dumps(chunk_str)[1:-1]
                yield escaped_chunk

        yield '"}'

