"""OneDrive / Outlook normalizers — text already extracted upstream."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.core.models import IdentityHint, PermissionLevel
from app.normalizer.base import NormalizerStrategy


class OneDriveNormalizer(NormalizerStrategy):
    def get_source_type(self) -> str:
        return "onedrive"

    async def extract_text(self, raw: Dict[str, Any]) -> str:
        for key in ("content", "body", "extractedText", "name", "title"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    def map_metadata(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        meta = (
            raw.get("structured_metadata")
            if isinstance(raw.get("structured_metadata"), dict)
            else {}
        )
        return {
            "mime_type": meta.get("mime_type") or raw.get("mimeType") or "",
            "file_extension": meta.get("file_extension") or "",
            "size_bytes": meta.get("size_bytes") or raw.get("size") or 0,
            "web_url": meta.get("web_url") or raw.get("webUrl") or "",
            "parent_path": meta.get("parent_path") or "",
            "created_by": meta.get("created_by") or "",
        }

    def extract_permission_hints(
        self, raw: Dict[str, Any]
    ) -> List[Tuple[IdentityHint, PermissionLevel]]:
        return []

    def extract_containers(self, raw: Dict[str, Any]) -> List[str]:
        parent = (raw.get("parentReference") or {}).get("id")
        return [str(parent)] if parent else []


class OutlookNormalizer(NormalizerStrategy):
    def get_source_type(self) -> str:
        return "outlook"

    async def extract_text(self, raw: Dict[str, Any]) -> str:
        for key in ("content", "bodyPreview", "body", "subject", "title"):
            value = raw.get(key)
            if isinstance(value, dict):
                value = value.get("content")
            if isinstance(value, str) and value.strip():
                return value
        return ""

    def map_metadata(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        meta = (
            raw.get("structured_metadata")
            if isinstance(raw.get("structured_metadata"), dict)
            else {}
        )
        return {
            "from_email": meta.get("from_email") or "",
            "to_emails": meta.get("to_emails") or [],
            "conversation_id": meta.get("conversation_id") or "",
            "has_attachments": bool(meta.get("has_attachments")),
            "importance": meta.get("importance") or "",
            "received_at": meta.get("received_at") or "",
        }

    def extract_permission_hints(
        self, raw: Dict[str, Any]
    ) -> List[Tuple[IdentityHint, PermissionLevel]]:
        return []

    def extract_containers(self, raw: Dict[str, Any]) -> List[str]:
        return []
