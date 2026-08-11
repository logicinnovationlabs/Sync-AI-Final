"""Core document reader logic: fetch, ACL gate, redact, structure preserve."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import HTTPException

from app.acl.acl_checker import ACLChecker, check_acl
from app.storage.document_store import DocumentStore

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

    # Never leak hidden_fields list content beyond what's needed
    if "hidden_fields" in visible and mode == "redacted":
        visible["hidden_fields"] = []

    return visible


def build_document_payload(
    *,
    doc_id: str,
    tenant_id: str,
    visible_metadata: Dict[str, Any],
    body: str,
    structured_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "document_id": doc_id,
        "tenant_id": tenant_id,
        "title": visible_metadata.get("title"),
        "body": body,
        "structured_metadata": structured_data or {},
        "created_at": _iso(visible_metadata.get("created_at")),
        "updated_at": _iso(visible_metadata.get("updated_at")),
        "owner_principal_id": visible_metadata.get("owner_principal_id"),
    }


async def read_document(
    doc_id: str,
    tenant_id: str,
    principal_id: str,
    store: DocumentStore,
    acl_checker: ACLChecker,
    *,
    load_body: bool = True,
) -> Dict[str, Any]:
    """
    Fetch metadata, ACL re-check (no cache), redact, optionally load body.
    """
    metadata = await store.get_metadata(tenant_id, doc_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Document not found")

    allowed = await check_acl(acl_checker, tenant_id, principal_id, doc_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="Forbidden")

    visible_metadata = redact_fields(metadata, principal_id)
    structured_data = await store.get_structured_metadata(tenant_id, doc_id)

    body = ""
    if load_body:
        object_key = metadata.get("object_key")
        if not object_key:
            raise HTTPException(status_code=500, detail="Document object missing")
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


async def stream_document_json(
    store: DocumentStore,
    object_key: str,
    doc_id: str,
    tenant_id: str,
    visible_metadata: Dict[str, Any],
    structured_data: Optional[Dict[str, Any]],
) -> AsyncGenerator[bytes, None]:
    """
    Stream a JSON document response with body filled chunk-wise.

    Yields UTF-8 bytes. Memory stays bounded to chunk size + prefix overhead.
    """
    prefix = {
        "document_id": doc_id,
        "tenant_id": tenant_id,
        "title": visible_metadata.get("title"),
        "structured_metadata": structured_data or {},
        "created_at": _iso(visible_metadata.get("created_at")),
        "updated_at": _iso(visible_metadata.get("updated_at")),
        "owner_principal_id": visible_metadata.get("owner_principal_id"),
    }
    # Emit: {"document_id":..., ..., "body":"
    opener = json.dumps(prefix, ensure_ascii=False)[:-1] + ',"body":"'
    yield opener.encode("utf-8")

    async for chunk in store.get_body_stream(object_key):
        text = chunk.decode("utf-8", errors="replace")
        escaped = (
            text.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        yield escaped.encode("utf-8")

    yield b'"}\n'
