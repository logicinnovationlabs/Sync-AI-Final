"""
Pipeline service for Block C.

Single integration point that orchestrates:
1. Normalization (MIME detection, text extraction, metadata mapping)
2. Identity resolution
3. ACL compilation (direct + inherited + group-expanded)
4. Persistence (CanonicalDocument + ACLEntry)
5. UnifiedDocument reconstruction with resolved permissions

Called by Celery tasks in place of connector.transform() + indexer.bulk_index().
"""

import logging
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone

MAX_EXTRACTED_CHARS = 500_000

from app.core.models import (
    CanonicalDocument,
    PermissionLevel,
)
from app.core.base_connector import UnifiedDocument
from app.normalizer.registry import normalizer_registry
from app.normalizer import mime_detector
from app.identity.resolver import IdentityResolver
from app.acl.compiler import ACLCompiler
from app.storage.canonical_repo import CanonicalRepo

# Import strategies to register them
import app.normalizer.strategies

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Block C pipeline orchestrator.
    
    Processes raw source documents through normalization, identity resolution,
    ACL compilation, and persistence.
    """
    
    def __init__(
        self,
        normalizer_registry,
        identity_resolver: IdentityResolver,
        acl_compiler: ACLCompiler,
        canonical_repo: CanonicalRepo,
    ):
        """
        Initialize pipeline.
        
        Args:
            normalizer_registry: Normalizer registry for strategy lookup
            identity_resolver: Identity resolver instance
            acl_compiler: ACL compiler instance
            canonical_repo: Repository for persistence
        """
        self.normalizer_registry = normalizer_registry
        self.identity_resolver = identity_resolver
        self.acl_compiler = acl_compiler
        self.canonical_repo = canonical_repo
    
    async def process_raw(
        self, raw: Dict[str, Any], source_type: str, tenant_id: UUID,
        connection_scope: Optional[str] = None, connected_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a raw source document through Block C pipeline.
        
        Returns dict with:
        - canonical_document: CanonicalDocument instance
        - acl_entries: List[ACLEntry]
        - unified_document: UnifiedDocument (ready for indexer.bulk_index())
        
        Args:
            raw: Raw document object from source
            source_type: Source type identifier
            tenant_id: Tenant ID for scoping
            connection_scope: Connector scope ("personal" or "organization")
            connected_by: User ID who connected the connector (for personal scope)
            
        Returns:
            Dict with canonical_document, acl_entries, unified_document
        """
        # 1. Get normalizer strategy
        strategy = self.normalizer_registry.get(source_type)
        
        # 2. MIME detection (cross-check magic bytes)
        detected_mime, mismatch = self._detect_mime(raw)
        
        # 3. Extract text (bounded, OCR-fallback-aware)
        content = await strategy.extract_text(raw)
        # Enforce hard upper bound regardless of strategy implementation
        if len(content) > MAX_EXTRACTED_CHARS:
            content = content[:MAX_EXTRACTED_CHARS]
        
        # 4. Map metadata
        metadata = strategy.map_metadata(raw)
        
        # 5. Extract containers
        containers = strategy.extract_containers(raw)
        
        source_id = raw.get("id", "")
        doc_id = f"{source_type}_{source_id}"

        # 6. Extract identity hints for special roles
        identity_hints = strategy.extract_identity_hints(raw)
        
        # 7. Resolve identities (Drive/Gmail bind to users.principal_id when
        # document_id is present — same UUID as ACL, no ghost metadata ids)
        resolved = {}
        for role, hint in identity_hints.items():
            try:
                resolved[role] = await self.identity_resolver.resolve(
                    hint, tenant_id, document_id=doc_id
                )
            except Exception as e:
                logger.error(f"Failed to resolve identity hint for role {role}: {e}")
        
        # 8. Build CanonicalDocument
        
        # Parse timestamps
        created_at = self._parse_timestamp(raw.get("createdTime") or raw.get("internalDate"))
        source_updated_at = self._parse_timestamp(raw.get("modifiedTime") or raw.get("internalDate"))
        
        # Determine owner_principal_id: for personal connectors, default to connected_by
        # if identity resolution returns pending (external email not a platform user)
        owner_id = None
        logger.info(f"DEBUG: connection_scope={connection_scope}, connected_by={connected_by}")
        if connection_scope == "personal" and connected_by:
            if resolved.get("owner") and not resolved["owner"].is_pending:
                owner_id = resolved["owner"].principal_id
            else:
                # Personal connector: use the user who connected it as owner
                try:
                    owner_id = UUID(connected_by)
                    logger.info(f"DEBUG: Setting owner_id from connected_by: {owner_id}")
                except (TypeError, ValueError):
                    logger.warning(f"Invalid connected_by UUID: {connected_by}")
        elif resolved.get("owner") and not resolved["owner"].is_pending:
            owner_id = resolved["owner"].principal_id
        
        doc = CanonicalDocument(
            id=doc_id,
            source_type=source_type,
            source_id=source_id,
            tenant_id=tenant_id,
            title=raw.get("name") or raw.get("subject") or self._extract_title(raw) or "Untitled",
            content=content,
            url=raw.get("webViewLink") or raw.get("url") or f"https://{source_type}/{source_id}",
            mime_type=raw.get("mimeType", "application/octet-stream"),
            detected_mime_type=detected_mime,
            mime_mismatch=mismatch,
            file_extension=raw.get("fileExtension"),
            size_bytes=self._parse_size(raw.get("size") or raw.get("sizeEstimate")),
            created_at=created_at,
            updated_at=datetime.now(timezone.utc),
            source_updated_at=source_updated_at,
            owner_principal_id=owner_id,
            creator_principal_id=(
                resolved["creator"].principal_id
                if resolved.get("creator") and not resolved["creator"].is_pending
                else None
            ),
            last_modifier_principal_id=(
                resolved["last_modifier"].principal_id
                if resolved.get("last_modifier") and not resolved["last_modifier"].is_pending
                else None
            ),
            structured_metadata=metadata,
            parent_ids=containers,
        )
        
        # 9. Extract permission hints
        permission_hints = strategy.extract_permission_hints(raw)
        
        # 10. Compile ACL
        acl_entries = await self.acl_compiler.compile(doc, permission_hints, tenant_id)
        
        # 11. Persist CanonicalDocument
        await self.canonical_repo.upsert_document(doc)
        
        # 12. Persist ACL entries (replace, not append)
        await self.canonical_repo.replace_acl_entries(doc.id, acl_entries)
        
        # 13. Build UnifiedDocument with resolved permissions
        unified_doc = self._build_unified_document(doc, acl_entries)
        
        return {
            "canonical_document": doc,
            "acl_entries": acl_entries,
            "unified_document": unified_doc,
        }
    
    def _extract_title(self, raw: Dict[str, Any]) -> str:
        """
        Fallback title extractor for sources that store the title inside nested
        structures (e.g. Gmail stores Subject inside payload.headers).
        """
        headers = raw.get("payload", {}).get("headers", [])
        for h in headers:
            if isinstance(h, dict) and h.get("name", "").lower() == "subject":
                return h.get("value", "") or ""
        return ""

    def _detect_mime(self, raw: Dict[str, Any]) -> tuple[str, bool]:
        """
        Detect MIME type from raw document.
        
        For in-memory tests, use pre-provided detected_mime or fall back to stated mime.
        For real implementation, would download file content and run magic-byte detection.
        """
        stated_mime = raw.get("mimeType")
        
        # Tests can inject detected_mime for mocking
        if "_test_detected_mime" in raw:
            detected = raw["_test_detected_mime"]
            mismatch = raw.get("_test_mime_mismatch", False)
            return detected, mismatch
        
        # For now, trust stated MIME in absence of real file bytes
        # Real implementation would: download file, mime_detector.detect_mime(bytes, stated_mime)
        return stated_mime or "application/octet-stream", False
    
    def _parse_timestamp(self, ts: Any) -> datetime:
        """Parse timestamp from various formats."""
        if isinstance(ts, datetime):
            return ts
        
        if isinstance(ts, int):
            # Unix timestamp in milliseconds (Gmail internalDate)
            return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        
        if isinstance(ts, str):
            # ISO 8601 timestamp
            try:
                # Remove timezone suffix for parsing
                import re
                clean_ts = re.sub(r'[+-]\d{2}:\d{2}$|Z$', '', ts)
                return datetime.fromisoformat(clean_ts).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        
        return datetime.now(timezone.utc)
    
    def _parse_size(self, size: Any) -> int:
        """Parse file size to int."""
        if isinstance(size, int):
            return size
        
        if isinstance(size, str):
            try:
                return int(size)
            except (ValueError, TypeError):
                pass
        
        return 0
    
    def _build_unified_document(
        self, doc: CanonicalDocument, acl_entries: list
    ) -> UnifiedDocument:
        """
        Build UnifiedDocument from CanonicalDocument with resolved permissions.
        
        Permissions are now "user:<uuid>" or "group:<uuid>" strings,
        not raw email strings.
        """
        # Convert ACL entries to resolved permission strings
        permissions = []
        for entry in acl_entries:
            if entry.principal_id:
                permissions.append(f"user:{entry.principal_id}")
            elif entry.group_id:
                permissions.append(f"group:{entry.group_id}")
        
        # Deduplicate
        permissions = list(set(permissions))
        
        unified = UnifiedDocument(
            id=doc.source_id,  # UnifiedDocument uses source_id, not canonical doc_id
            title=doc.title,
            content=doc.content,
            source_type=doc.source_type,
            url=doc.url,
            permissions=permissions,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            source_updated_at=doc.source_updated_at,
            structured_metadata=doc.structured_metadata,
        )
        
        return unified
