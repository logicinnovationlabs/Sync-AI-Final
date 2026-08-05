"""
Canonical repository for Block C persistence.

Handles CanonicalDocument, Principal, Group, ACLEntry, ContainerACLEntry,
and ContainerEdge persistence in the per-tenant Postgres database.

All operations are tenant-scoped via Block A's TenantResolver-provisioned connection.
"""

import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.core.models import (
    CanonicalDocument,
    Principal,
    Group,
    ACLEntry,
    ContainerACLEntry,
    ContainerEdge,
)

logger = logging.getLogger(__name__)


class CanonicalRepo:
    """
    Repository for canonical document and ACL persistence.
    
    Uses in-memory storage for tests. Real implementation would use SQLAlchemy
    with Block A's tenant-scoped database connection.
    """
    
    def __init__(self, use_memory: bool = True):
        """
        Initialize repository.
        
        Args:
            use_memory: If True, use in-memory storage (for tests)
        """
        self.use_memory = use_memory
        
        # In-memory storage (for tests)
        self._documents: dict[str, CanonicalDocument] = {}
        self._principals: dict[UUID, Principal] = {}
        self._principals_by_email: dict[tuple[UUID, str], Principal] = {}
        self._groups: dict[UUID, Group] = {}
        self._groups_by_email: dict[tuple[UUID, str], Group] = {}
        self._groups_by_source: dict[tuple[str, str, UUID], Group] = {}
        self._acl_entries: dict[str, List[ACLEntry]] = {}  # {document_id: [entries]}
        self._container_acl_entries: dict[tuple[str, UUID], List[ContainerACLEntry]] = {}
        self._container_edges: dict[tuple[str, UUID], Optional[str]] = {}  # {(child_id, tenant_id): parent_id}
    
    # ============================================================
    # CANONICAL DOCUMENT METHODS
    # ============================================================
    
    async def upsert_document(self, doc: CanonicalDocument) -> None:
        """Create or update a CanonicalDocument."""
        if self.use_memory:
            self._documents[doc.id] = doc
        else:
            # Real implementation: SQLAlchemy upsert via tenant-scoped session
            pass
    
    async def get_document(self, document_id: str) -> Optional[CanonicalDocument]:
        """Get a CanonicalDocument by ID."""
        if self.use_memory:
            return self._documents.get(document_id)
        else:
            pass
    
    async def delete_documents_and_acls(self, document_ids: List[str], tenant_id: UUID) -> None:
        """Delete documents and their ACL entries."""
        if self.use_memory:
            for doc_id in document_ids:
                self._documents.pop(doc_id, None)
                self._acl_entries.pop(doc_id, None)
        else:
            pass
    
    # ============================================================
    # PRINCIPAL METHODS
    # ============================================================
    
    async def create_principal(self, principal: Principal) -> None:
        """
        Create a new principal.
        
        Raises exception on uniqueness constraint violation (tenant_id, lower(email)).
        """
        if self.use_memory:
            # Check uniqueness
            email_key = (principal.tenant_id, principal.email.lower())
            if email_key in self._principals_by_email:
                raise ValueError(
                    f"Principal with email {principal.email} already exists in tenant {principal.tenant_id}"
                )
            
            self._principals[principal.id] = principal
            self._principals_by_email[email_key] = principal
        else:
            pass
    
    async def update_principal(self, principal: Principal) -> None:
        """Update an existing principal."""
        if self.use_memory:
            self._principals[principal.id] = principal
            email_key = (principal.tenant_id, principal.email.lower())
            self._principals_by_email[email_key] = principal
        else:
            pass
    
    async def get_principal_by_email(
        self, email: str, tenant_id: UUID
    ) -> Optional[Principal]:
        """
        Get principal by email (case-insensitive, tenant-scoped).
        """
        if self.use_memory:
            email_key = (tenant_id, email.lower())
            return self._principals_by_email.get(email_key)
        else:
            pass
    
    async def get_principal_by_source_identity(
        self, source_type: str, external_id: str, tenant_id: UUID
    ) -> Optional[Principal]:
        """
        Get principal by source_identities mapping.
        """
        if self.use_memory:
            for principal in self._principals.values():
                if principal.tenant_id == tenant_id:
                    if principal.source_identities.get(source_type) == external_id:
                        return principal
            return None
        else:
            pass
    
    # ============================================================
    # GROUP METHODS
    # ============================================================
    
    async def create_group(self, group: Group) -> None:
        """Create a new group."""
        if self.use_memory:
            self._groups[group.id] = group
            if group.email:
                email_key = (group.tenant_id, group.email.lower())
                self._groups_by_email[email_key] = group
            source_key = (group.source_type, group.source_id, group.tenant_id)
            self._groups_by_source[source_key] = group
        else:
            pass
    
    async def get_group(self, group_id: UUID, tenant_id: UUID) -> Optional[Group]:
        """Get group by ID."""
        if self.use_memory:
            group = self._groups.get(group_id)
            if group and group.tenant_id == tenant_id:
                return group
            return None
        else:
            pass
    
    async def get_group_by_email(
        self, email: str, tenant_id: UUID
    ) -> Optional[Group]:
        """Get group by email (case-insensitive, tenant-scoped)."""
        if self.use_memory:
            email_key = (tenant_id, email.lower())
            return self._groups_by_email.get(email_key)
        else:
            pass
    
    async def get_group_by_source_identity(
        self, source_type: str, source_id: str, tenant_id: UUID
    ) -> Optional[Group]:
        """Get group by source identity."""
        if self.use_memory:
            source_key = (source_type, source_id, tenant_id)
            return self._groups_by_source.get(source_key)
        else:
            pass
    
    # ============================================================
    # ACL ENTRY METHODS
    # ============================================================
    
    async def replace_acl_entries(
        self, document_id: str, entries: List[ACLEntry]
    ) -> None:
        """
        Replace ACL entries for a document (not append).
        
        This ensures revoked permissions actually disappear.
        """
        if self.use_memory:
            self._acl_entries[document_id] = entries
        else:
            pass
    
    async def get_acl_entries(self, document_id: str) -> List[ACLEntry]:
        """Get ACL entries for a document."""
        if self.use_memory:
            return self._acl_entries.get(document_id, [])
        else:
            pass
    
    # ============================================================
    # CONTAINER ACL ENTRY METHODS
    # ============================================================
    
    async def upsert_container_acl(self, entry: ContainerACLEntry) -> None:
        """Create or update a container ACL entry."""
        if self.use_memory:
            key = (entry.container_id, entry.tenant_id)
            if key not in self._container_acl_entries:
                self._container_acl_entries[key] = []
            
            # Remove existing entry for same principal/group
            existing = self._container_acl_entries[key]
            existing[:] = [
                e for e in existing
                if not (e.principal_id == entry.principal_id and e.group_id == entry.group_id)
            ]
            
            existing.append(entry)
        else:
            pass
    
    async def get_container_acl_entries(
        self, container_id: str, tenant_id: UUID
    ) -> List[ContainerACLEntry]:
        """Get container ACL entries."""
        if self.use_memory:
            key = (container_id, tenant_id)
            return self._container_acl_entries.get(key, [])
        else:
            pass
    
    # ============================================================
    # CONTAINER EDGE METHODS
    # ============================================================
    
    async def upsert_container_edge(self, edge: ContainerEdge) -> None:
        """Create or update a container edge."""
        if self.use_memory:
            key = (edge.child_container_id, edge.tenant_id)
            self._container_edges[key] = edge.parent_container_id
        else:
            pass
    
    async def get_parent_container(
        self, child_id: str, tenant_id: UUID
    ) -> Optional[str]:
        """Get parent container ID for a child."""
        if self.use_memory:
            key = (child_id, tenant_id)
            return self._container_edges.get(key)
        else:
            pass
    
    async def delete_container(self, container_id: str, tenant_id: UUID) -> None:
        """Delete container and its edges."""
        if self.use_memory:
            # Delete container ACL entries
            key = (container_id, tenant_id)
            self._container_acl_entries.pop(key, None)
            
            # Delete edges where this is parent or child
            keys_to_delete = [
                k for k, v in self._container_edges.items()
                if k[0] == container_id or v == container_id
            ]
            for k in keys_to_delete:
                self._container_edges.pop(k, None)
        else:
            pass
