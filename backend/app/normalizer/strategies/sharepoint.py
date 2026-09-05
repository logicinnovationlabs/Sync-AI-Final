"""
SharePoint normalizer strategy.

Extracts text, metadata, and permission hints from Graph driveItem objects
so ACLCompiler can write the same acl_filter_terms shape used by Drive.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from app.normalizer.base import NormalizerStrategy
from app.core.models import IdentityHint, PermissionLevel
from app.core.config import settings

logger = logging.getLogger(__name__)


class SharePointNormalizer(NormalizerStrategy):
    def get_source_type(self) -> str:
        return "sharepoint"

    def _bound(self, text: str) -> str:
        max_chars = int(getattr(settings, "max_extracted_chars", 500000) or 500000)
        if text and len(text) > max_chars:
            return text[:max_chars]
        return text or ""

    async def extract_text(self, raw: Dict[str, Any]) -> str:
        injected = raw.get("_test_extracted_text") or raw.get("_extracted_text")
        if isinstance(injected, str) and injected.strip():
            return self._bound(injected)
        for key in ("extractedText", "fullText", "content", "body"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return self._bound(value)
        return self._bound(raw.get("name") or "")

    def map_metadata(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        file_obj = raw.get("file") or {}
        mime_type = raw.get("mimeType") or file_obj.get("mimeType") or ""
        name = raw.get("name") or ""
        file_extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        size_bytes = raw.get("size") or 0
        try:
            size_bytes = int(size_bytes)
        except (TypeError, ValueError):
            size_bytes = 0
        created = (raw.get("createdBy") or {}).get("user") or {}
        owner_email = created.get("email") or created.get("userPrincipalName") or ""
        return {
            "mime_type": mime_type,
            "file_extension": file_extension,
            "owner_email": owner_email,
            "site_id": raw.get("_site_id") or "",
            "site_name": raw.get("_site_name") or "",
            "drive_id": raw.get("_drive_id") or "",
            "parent_folder_id": (raw.get("parentReference") or {}).get("id") or "",
            "web_view_link": raw.get("webViewLink") or raw.get("webUrl") or "",
            "size_bytes": size_bytes,
            "visibility_mode": "restricted",
        }

    def extract_permission_hints(self, raw: Dict[str, Any]) -> List[Tuple[IdentityHint, PermissionLevel]]:
        hints: List[Tuple[IdentityHint, PermissionLevel]] = []
        skipped_non_user = 0
        seen_emails = set()

        for perm in raw.get("permissions") or []:
            identity = (
                perm.get("grantedToV2")
                or perm.get("grantedTo")
                or {}
            )
            user = identity.get("user") or {}
            email = (user.get("email") or user.get("userPrincipalName") or "").strip().lower()
            roles = [str(r).lower() for r in (perm.get("roles") or [])]
            link = perm.get("link") or {}
            if link.get("scope") in {"anonymous", "organization", "users"}:
                skipped_non_user += 1
                continue
            if not email:
                if identity.get("group") or identity.get("siteGroup"):
                    skipped_non_user += 1
                continue
            if email in seen_emails:
                continue
            seen_emails.add(email)
            if "owner" in roles:
                level = PermissionLevel.OWNER
            elif "write" in roles:
                level = PermissionLevel.WRITE
            else:
                level = PermissionLevel.READ
            hints.append(
                (
                    IdentityHint(
                        source_type="sharepoint",
                        external_id=str(user.get("id") or email),
                        email=email,
                        name=user.get("displayName"),
                    ),
                    level,
                )
            )

        if skipped_non_user:
            logger.info(
                "skipped %s non-user SharePoint permission(s) item=%s",
                skipped_non_user,
                raw.get("id"),
            )

        if not hints:
            created = (raw.get("createdBy") or {}).get("user") or {}
            email = (created.get("email") or created.get("userPrincipalName") or "").strip().lower()
            if email:
                hints.append(
                    (
                        IdentityHint(
                            source_type="sharepoint",
                            external_id=str(created.get("id") or email),
                            email=email,
                            name=created.get("displayName"),
                        ),
                        PermissionLevel.OWNER,
                    )
                )
        return hints

    def extract_containers(self, raw: Dict[str, Any]) -> List[str]:
        return []

    def extract_identity_hints(self, raw: Dict[str, Any]) -> Dict[str, IdentityHint]:
        hints: Dict[str, IdentityHint] = {}
        created = (raw.get("createdBy") or {}).get("user") or {}
        email = created.get("email") or created.get("userPrincipalName")
        if email:
            owner = IdentityHint(
                source_type="sharepoint",
                external_id=str(created.get("id") or email),
                email=email,
                name=created.get("displayName"),
            )
            hints["owner"] = owner
            hints["creator"] = owner
        modified = (raw.get("lastModifiedBy") or {}).get("user") or {}
        mod_email = modified.get("email") or modified.get("userPrincipalName")
        if mod_email:
            hints["last_modifier"] = IdentityHint(
                source_type="sharepoint",
                external_id=str(modified.get("id") or mod_email),
                email=mod_email,
                name=modified.get("displayName"),
            )
        return hints
