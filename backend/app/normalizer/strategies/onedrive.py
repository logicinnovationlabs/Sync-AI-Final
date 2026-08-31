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

    def extract_identity_hints(self, raw: Dict[str, Any]) -> Dict[str, IdentityHint]:
        """Extract creator and last modifier hints from OneDrive item metadata.

        OneDrive Graph API returns:
          raw["createdBy"]["user"]["email"]       — file creator
          raw["lastModifiedBy"]["user"]["email"]  — last modifier
        The connector.transform() path stores creator in structured_metadata["created_by"]
        as a fallback.
        """
        hints = {}

        # Creator: createdBy.user.email / userPrincipalName
        created_by_user = (raw.get("createdBy") or {}).get("user") or {}
        creator_email = (
            created_by_user.get("email")
            or created_by_user.get("userPrincipalName")
            or ""
        )
        creator_name = created_by_user.get("displayName") or ""
        if creator_email:
            hints["owner"] = IdentityHint(
                source_type="onedrive",
                external_id=creator_email.lower(),
                email=creator_email.lower(),
                name=creator_name or None,
            )
            hints["creator"] = hints["owner"]

        # Last modifier: lastModifiedBy.user.email
        last_mod_user = (raw.get("lastModifiedBy") or {}).get("user") or {}
        modifier_email = (
            last_mod_user.get("email")
            or last_mod_user.get("userPrincipalName")
            or ""
        )
        modifier_name = last_mod_user.get("displayName") or ""
        if modifier_email and modifier_email.lower() != creator_email.lower():
            hints["last_modifier"] = IdentityHint(
                source_type="onedrive",
                external_id=modifier_email.lower(),
                email=modifier_email.lower(),
                name=modifier_name or None,
            )

        # Fallback: structured_metadata["created_by"] set by connector.transform()
        if not hints:
            meta = raw.get("structured_metadata") or {}
            created_by_email = meta.get("created_by") or ""
            if created_by_email:
                hints["owner"] = IdentityHint(
                    source_type="onedrive",
                    external_id=created_by_email.lower(),
                    email=created_by_email.lower(),
                    name=None,
                )
                hints["creator"] = hints["owner"]

        return hints


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

    def extract_identity_hints(self, raw: Dict[str, Any]) -> Dict[str, IdentityHint]:
        """Extract sender identity hint from Outlook message.

        Outlook Graph API raw shape:
          raw["from"]["emailAddress"]["address"]  — sender email
          raw["from"]["emailAddress"]["name"]     — sender display name

        Fallback: structured_metadata["from_email"] set by connector.transform().
        """
        hints = {}

        # Sender: raw["from"]["emailAddress"]["address"]
        frm = raw.get("from") or {}
        email_addr_obj = frm.get("emailAddress") or {}
        sender_email = email_addr_obj.get("address") or ""
        sender_name = email_addr_obj.get("name") or ""

        # Fallback: structured_metadata set by connector.transform()
        if not sender_email:
            meta = raw.get("structured_metadata") or {}
            sender_email = meta.get("from_email") or ""

        if sender_email:
            hint = IdentityHint(
                source_type="outlook",
                external_id=sender_email.lower(),
                email=sender_email.lower(),
                name=sender_name or None,
            )
            hints["creator"] = hint
            # Sender is the "owner" of this mailbox item for ACL resolution
            hints["owner"] = hint

        return hints
