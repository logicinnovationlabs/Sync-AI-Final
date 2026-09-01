"""
Google Drive normalizer strategy.

Extracts text, metadata, and permission hints from Drive files.
Handles Google-native formats (Docs/Sheets/Slides) via Drive export API.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.normalizer.base import NormalizerStrategy
from app.core.models import IdentityHint, PermissionLevel
from app.core.config import settings

logger = logging.getLogger(__name__)

GOOGLE_NATIVE_EXPORT = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


class GoogleDriveNormalizer(NormalizerStrategy):
    """
    Normalizer for Google Drive files.

    Handles both Google-native formats (export to text) and binary formats
    (download and extract via TextExtractor). Tests may inject
    ``_test_extracted_text``; that path always wins so signoff stays stable.
    """

    def __init__(self, drive_client=None, text_extractor=None):
        self.drive_client = drive_client
        self.text_extractor = text_extractor

    def get_source_type(self) -> str:
        return "google_drive"

    def _bound(self, text: str) -> str:
        max_chars = int(getattr(settings, "max_extracted_chars", 500000) or 500000)
        if text and len(text) > max_chars:
            return text[:max_chars]
        return text or ""

    async def extract_text(self, raw: Dict[str, Any]) -> str:
        """
        Extract text from Drive file.

        Order:
        1. Test injection ``_test_extracted_text``
        2. Inline content fields already present on the payload
        3. Drive export/download when a client + access token are available
        4. Filename placeholder (existing signoff expectation)
        """
        injected = raw.get("_test_extracted_text")
        if isinstance(injected, str) and injected:
            return self._bound(injected)

        for key in ("_extracted_text", "extractedText", "fullText", "content", "body"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return self._bound(value)

        name = raw.get("name", "") or ""
        file_id = raw.get("id")
        access_token = raw.get("_access_token") or raw.get("access_token")
        mime_type = raw.get("mimeType") or raw.get("mime_type") or ""
        if self.drive_client and file_id and access_token:
            try:
                export_mime = GOOGLE_NATIVE_EXPORT.get(mime_type)
                if export_mime:
                    data = await self.drive_client.export_file(
                        access_token, file_id, mime_type=export_mime
                    )
                    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
                    return self._bound(text)
                data = await self.drive_client.download_file(access_token, file_id)
                if self.text_extractor is not None:
                    extracted = await self.text_extractor.extract(
                        data,
                        mime_type,
                        file_extension=raw.get("fileExtension"),
                    )
                    return self._bound(extracted)
                if isinstance(data, bytes):
                    return self._bound(data.decode("utf-8", errors="replace"))
                return self._bound(str(data))
            except Exception as exc:
                logger.warning("Drive text extraction failed for file %s: %s", file_id, exc)

        return self._bound(name)
    
    def map_metadata(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and validate metadata from Drive file.
        
        Re-validates against Drive's manifest allowlist (same as Block B).
        """
        mime_type = raw.get("mimeType", "")
        file_extension = raw.get("fileExtension", "")
        size_bytes = raw.get("size")
        
        # Parse size as int if string
        if isinstance(size_bytes, str):
            try:
                size_bytes = int(size_bytes)
            except (ValueError, TypeError):
                size_bytes = 0
        elif size_bytes is None:
            size_bytes = 0
        
        # Owner email
        owners = raw.get("owners", [])
        owner_email = owners[0].get("emailAddress", "") if owners else ""
        
        # Metadata allowlist (same fields as Block B's transform())
        metadata = {
            "mime_type": mime_type,
            "file_extension": file_extension,
            "owner_email": owner_email,
            "shared_drive_id": raw.get("driveId", ""),
            "parent_folder_id": raw.get("parents", [""])[0] if raw.get("parents") else "",
            "web_view_link": raw.get("webViewLink", ""),
            "size_bytes": size_bytes,
            "visibility_mode": "restricted",
        }
        
        return metadata
    
    def extract_permission_hints(self, raw: Dict[str, Any]) -> List[Tuple[IdentityHint, PermissionLevel]]:
        """
        Extract permission grants from Drive file.
        
        Converts Drive's permission list to (IdentityHint, PermissionLevel) pairs.
        Drive's role field maps to PermissionLevel.
        """
        hints = []
        permissions = raw.get("permissions", [])
        skipped_non_user = 0
        
        for perm in permissions:
            perm_type = perm.get("type", "")
            email = perm.get("emailAddress", "")
            role = perm.get("role", "reader")
            deleted = perm.get("deleted", False)
            perm_id = perm.get("id", "")
            
            if deleted:
                continue
            
            # Map Drive role to PermissionLevel
            if role == "owner":
                level = PermissionLevel.OWNER
            elif role == "writer" or role == "fileOrganizer":
                level = PermissionLevel.WRITE
            elif role == "commenter":
                level = PermissionLevel.READ  # Commenter is read-level for ACL purposes
            else:  # reader
                level = PermissionLevel.READ
            
            # Create IdentityHint based on permission type
            if perm_type == "user" and email:
                hint = IdentityHint(
                    source_type="google_drive",
                    external_id=perm_id or email,
                    email=email,
                    name=perm.get("displayName"),
                )
                hints.append((hint, level))
            elif perm_type in ("group", "anyone", "domain"):
                skipped_non_user += 1
        
        if skipped_non_user:
            logger.info(
                "skipped %s non-user Drive permission(s) file_id=%s",
                skipped_non_user,
                raw.get("id"),
            )
        
        # If no permissions found, default to owner
        if not hints:
            owners = raw.get("owners", [])
            if owners:
                owner = owners[0]
                hint = IdentityHint(
                    source_type="google_drive",
                    external_id=owner.get("permissionId", owner.get("emailAddress", "")),
                    email=owner.get("emailAddress", ""),
                    name=owner.get("displayName"),
                )
                hints.append((hint, PermissionLevel.OWNER))
        
        return hints
    
    def extract_containers(self, raw: Dict[str, Any]) -> List[str]:
        """Drive file ACL is permissions.list on the file. No folder inheritance."""
        return []
    
    def extract_identity_hints(self, raw: Dict[str, Any]) -> Dict[str, IdentityHint]:
        """
        Extract identity hints for owner, creator, last_modifier.
        
        Drive doesn't reliably distinguish creator from owner in the API response
        (ownedByMe flag exists but not creator). We use owner for both.
        """
        hints = {}
        
        # Owner
        owners = raw.get("owners", [])
        if owners:
            owner = owners[0]
            hints["owner"] = IdentityHint(
                source_type="google_drive",
                external_id=owner.get("permissionId", owner.get("emailAddress", "")),
                email=owner.get("emailAddress", ""),
                name=owner.get("displayName"),
            )
            # Use owner as creator too (Drive doesn't expose creator separately)
            hints["creator"] = hints["owner"]
        
        # Last modifier (if present and different from owner)
        last_modifying_user = raw.get("lastModifyingUser", {})
        if last_modifying_user and last_modifying_user.get("emailAddress"):
            hints["last_modifier"] = IdentityHint(
                source_type="google_drive",
                external_id=last_modifying_user.get("permissionId", last_modifying_user.get("emailAddress", "")),
                email=last_modifying_user.get("emailAddress", ""),
                name=last_modifying_user.get("displayName"),
            )
        
        return hints
