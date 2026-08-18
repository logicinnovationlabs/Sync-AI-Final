"""
Google Drive normalizer strategy.

Extracts text, metadata, and permission hints from Drive files.
Handles Google-native formats (Docs/Sheets/Slides) via Drive export API.
"""

import logging
from typing import Dict, Any, List, Tuple
from app.normalizer.base import NormalizerStrategy
from app.core.models import IdentityHint, PermissionLevel

logger = logging.getLogger(__name__)


class GoogleDriveNormalizer(NormalizerStrategy):
    """
    Normalizer for Google Drive files.
    
    Handles both Google-native formats (export to text) and binary formats
    (download and extract via TextExtractor).
    """
    
    def get_source_type(self) -> str:
        return "google_drive"
    
    async def extract_text(self, raw: Dict[str, Any]) -> str:
        """
        Extract text from Drive file.
        
        For Google-native formats (Docs/Sheets/Slides), export via Drive API.
        For binary formats (PDF/DOCX/etc.), download and route through TextExtractor.
        
        NOTE: This is a simplified implementation. Real implementation would need
        access to DriveClient and TextExtractor, which should be injected via
        constructor. For now, we return file name as placeholder (tests will mock).
        """
        # In real implementation, this would:
        # 1. Check mime_type
        # 2. For Google-native: call drive_client.export_file(file_id, mime_type="text/plain")
        # 3. For binary: call drive_client.download_file(file_id), then text_extractor.extract()
        # 4. Return extracted text
        
        # Placeholder: prefer connector-extracted text, then test injection, then name
        name = raw.get("name", "")
        snippet = raw.get("_extracted_text") or raw.get("_test_extracted_text", name)
        return snippet
    
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
            elif perm_type == "group" and email:
                # Groups will be resolved separately in ACLCompiler
                hint = IdentityHint(
                    source_type="google_drive",
                    external_id=perm_id or email,
                    email=email,
                    name=perm.get("displayName"),
                )
                hints.append((hint, level))
            elif perm_type == "anyone":
                # Public file — use special wildcard principal
                hint = IdentityHint(
                    source_type="google_drive",
                    external_id="anyone",
                    email="*",
                    name="Anyone with the link",
                )
                hints.append((hint, level))
        
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
        """
        Extract parent folder IDs for inheritance.
        
        Drive files can have multiple parents (though uncommon after My Drive changes).
        """
        parents = raw.get("parents", [])
        return parents if isinstance(parents, list) else []
    
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
