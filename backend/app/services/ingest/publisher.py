"""Publish Google connector raw objects onto ingest.raw.v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.event_bus import producer

INGEST_RAW_TOPIC = "ingest.raw.v1"


def _topic() -> str:
    # Prefer the architecture topic name; fall back to env alias if it is already ingest.raw.v1.
    configured = (getattr(settings, "kafka_topic_raw", None) or "").strip()
    if configured in ("ingest.raw.v1", "ingest-raw", ""):
        return INGEST_RAW_TOPIC
    return configured


def raw_event_from_item(
    *,
    tenant_id: str,
    source_type: str,
    source_instance_id: str,
    item: Any,
) -> Dict[str, Any]:
    payload = item if isinstance(item, dict) else dict(getattr(item, "__dict__", {}) or {})
    object_id = str(payload.get("id") or payload.get("fileId") or payload.get("messageId") or "")
    perms = payload.get("permissions")
    if not isinstance(perms, list):
        perms = []
    identity_refs: List[Any] = []
    for perm in perms:
        if isinstance(perm, dict):
            email = perm.get("emailAddress") or perm.get("email")
            if email:
                identity_refs.append({"type": "email", "value": email})
    mailbox = payload.get("_mailbox_email")
    if mailbox:
        identity_refs.append({"type": "email", "value": mailbox})
    return {
        "tenant_id": tenant_id,
        "source_type": source_type,
        "source_instance_id": source_instance_id,
        "source_object_id": object_id,
        "object_kind": "file" if source_type == "google_drive" else "message",
        "raw_payload": payload,
        "raw_acls": perms,
        "identity_refs": identity_refs,
        "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
    }


def publish_raw_event(event: Dict[str, Any]) -> None:
    producer.send(_topic(), value=event, key=str(event.get("source_object_id") or ""))


def publish_google_item(
    *,
    tenant_id: str,
    source_type: str,
    source_instance_id: str,
    item: Any,
) -> Dict[str, Any]:
    event = raw_event_from_item(
        tenant_id=tenant_id,
        source_type=source_type,
        source_instance_id=source_instance_id,
        item=item,
    )
    publish_raw_event(event)
    return event
