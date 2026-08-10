"""Consumer for ingest.canonical.v1 events from Block C."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.services.acl_filter import normalize_acl_terms
from app.services.factory import get_lexical_store

logger = logging.getLogger(__name__)


def _extract_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map canonical event payload to indexed fields."""
    meta = payload.get("structured_metadata") or payload.get("metadata") or {}
    content = payload.get("content") or payload.get("body_text") or ""
    acl = (
        payload.get("acl_filter_terms")
        or payload.get("acl_terms")
        or meta.get("acl_filter_terms")
        or []
    )
    return {
        "title": payload.get("title") or meta.get("title") or "",
        "body_text": content if isinstance(content, str) else str(content),
        "comments_text": payload.get("comments_text") or meta.get("comments_text") or "",
        "file_path": payload.get("file_path") or meta.get("file_path") or "",
        "repository": payload.get("repository") or meta.get("repository") or "",
        "object_type": payload.get("object_type")
        or payload.get("content_type")
        or meta.get("object_type")
        or "document",
        "source": payload.get("source") or meta.get("source") or "",
        "owner": payload.get("owner") or meta.get("owner") or "",
        "updated_at": payload.get("updated_at") or meta.get("updated_at"),
        "container_path": payload.get("container_path") or meta.get("container_path") or "",
        "language": payload.get("language") or meta.get("language") or "",
        "tags": list(payload.get("tags") or meta.get("tags") or []),
        "acl_filter_terms": normalize_acl_terms(acl),
        "hidden_fields": list(payload.get("hidden_fields") or []),
    }


class CanonicalConsumer:
    """Process ingest.canonical.v1 envelopes into the lexical index."""

    def __init__(self, store=None) -> None:
        self.store = store or get_lexical_store()

    async def process_event(self, event: Dict[str, Any]) -> Optional[str]:
        """
        Accept envelope:
          { "tenant_id": "...", "payload": { "document_id": "...", ... } }
        or flat canonical document with tenant_id + document_id.
        """
        tenant_id = event.get("tenant_id")
        payload = event.get("payload") or event
        if not tenant_id:
            tenant_id = payload.get("tenant_id")
        document_id = payload.get("document_id") or payload.get("id")
        if not tenant_id or not document_id:
            logger.error("canonical event missing tenant_id/document_id: %s", event)
            return None

        deleted = bool(payload.get("deleted") or payload.get("is_deleted"))
        fields = _extract_fields(payload)
        await self.store.index_document(
            tenant_id=str(tenant_id),
            document_id=str(document_id),
            fields=fields,
            deleted=deleted,
        )
        logger.info(
            "Indexed canonical doc=%s tenant=%s deleted=%s",
            document_id,
            tenant_id,
            deleted,
        )
        return str(document_id)
