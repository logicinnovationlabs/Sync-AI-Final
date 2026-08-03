"""
ACL compiler for materializing document permissions.

Compiles direct grants + inherited permissions + group expansion into ACLEntry rows.
Persists to Postgres for query-time filtering.
"""

import logging
from typing import List, Tuple, Set, Dict
from uuid import UUID
from datetime import datetime, timezone

from app.core.models import (
    CanonicalDocument,
    IdentityHint,
    PermissionLevel,
    ACLEntry,
    Principal,
    Group,
)
from app.acl.container_service import ContainerService
from app.acl.inheritance import compute_inherited_entries
from app.identity.resolver import IdentityResolver

logger = logging.getLogger(__name__)


class ACLCompiler:
    """
    Compiles and materializes ACLs for documents.
    
    Process:
    1. Resolve permission hints to principal_id/group_id
    2. Add direct entries
    3. Add inherited entries from container ancestors
    4. Expand group membership (cycle-safe)
    5. Apply deny overrides
    6. Persist to Postgres (replace, not append)
    """
    
    def __init__(
        self,
        identity_resolver: IdentityResolver,
        container_service: ContainerService,
        canonical_repo,
    ):
        """
        Initialize ACL compiler.
        
        Args:
            identity_resolver: Identity resolver for hint resolution
            container_service: Container service for inheritance
            canonical_repo: Repository for persistence
        """
        self.identity_resolver = identity_resolver
        self.container_service = container_service
        self.repo = canonical_repo
    
    async def compile(
        self,
        document: CanonicalDocument,
        permission_hints: List[Tuple[IdentityHint, PermissionLevel]],
        tenant_id: UUID,
    ) -> List[ACLEntry]:
        """
        Compile full ACL for a document.
        
        Args:
            document: CanonicalDocument instance
            permission_hints: List of (IdentityHint, PermissionLevel) tuples
            tenant_id: Tenant ID for scoping
            
        Returns:
            List of compiled ACLEntry objects (not yet persisted)
        """
        all_entries: List[ACLEntry] = []
        
        # 1. Resolve permission hints and create direct entries
        direct_entries = await self._compile_direct_entries(
            document, permission_hints, tenant_id
        )
        all_entries.extend(direct_entries)
        
        # 2. Compute inherited entries from containers
        inherited_entries = await compute_inherited_entries(
            document, self.container_service
        )
        all_entries.extend(inherited_entries)
        
        # 3. Expand group membership (cycle-safe)
        expanded_entries = await self._expand_group_membership(all_entries, tenant_id)
        all_entries.extend(expanded_entries)
        
        # 4. Apply deny overrides and deduplicate
        final_entries = self._apply_deny_overrides(all_entries)
        
        return final_entries
    
    async def _compile_direct_entries(
        self,
        document: CanonicalDocument,
        permission_hints: List[Tuple[IdentityHint, PermissionLevel]],
        tenant_id: UUID,
    ) -> List[ACLEntry]:
        """
        Compile direct permission entries from hints.
        
        Resolves identity hints to principal_id or group_id.
        """
        direct_entries: List[ACLEntry] = []
        
        for hint, level in permission_hints:
            # Determine if this is a group or individual
            # Groups have email patterns like "group@example.com" or type hints
            is_group = await self._is_group_hint(hint, tenant_id)
            
            if is_group:
                # Resolve to group_id
                group = await self._resolve_group(hint, tenant_id)
                if not group:
                    logger.warning(f"Could not resolve group hint: {hint}")
                    continue
                
                entry = ACLEntry(
                    document_id=document.id,
                    principal_id=None,
                    group_id=group.id,
                    permission=level,
                    granted_via="direct",
                    source_container_id=None,
                    is_deny=False,
                    source_type=document.source_type,
                    tenant_id=tenant_id,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                direct_entries.append(entry)
            else:
                # Resolve to principal_id
                try:
                    resolved = await self.identity_resolver.resolve(hint, tenant_id)
                    entry = ACLEntry(
                        document_id=document.id,
                        principal_id=resolved.principal_id,
                        group_id=None,
                        permission=level,
                        granted_via="direct",
                        source_container_id=None,
                        is_deny=False,
                        source_type=document.source_type,
                        tenant_id=tenant_id,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    direct_entries.append(entry)
                except Exception as e:
                    logger.error(f"Failed to resolve identity hint {hint}: {e}")
        
        return direct_entries
    
    async def _is_group_hint(self, hint: IdentityHint, tenant_id: UUID) -> bool:
        """
        Determine if a hint represents a group.
        
        Heuristic: Check if external_id starts with "group:" or if the hint
        came from a permission with type="group" (normalized strategies should
        preserve this in external_id prefix).
        """
        # Check external_id for group prefix
        if hint.external_id.startswith("group:"):
            return True
        
        # Check if a group with this email exists
        if hint.email:
            group = await self.repo.get_group_by_email(hint.email, tenant_id)
            if group:
                return True
        
        return False
    
    async def _resolve_group(self, hint: IdentityHint, tenant_id: UUID) -> Group | None:
        """
        Resolve identity hint to a Group.
        
        Matches on (source_type, external_id) or email.
        Creates new Group if not found.
        """
        # Try matching by source_type + source_id
        group = await self.repo.get_group_by_source_identity(
            hint.source_type, hint.external_id, tenant_id
        )
        
        if group:
            return group
        
        # Try matching by email
        if hint.email:
            group = await self.repo.get_group_by_email(hint.email, tenant_id)
            if group:
                return group
        
        # Create new group
        from uuid import uuid4
        group = Group(
            id=uuid4(),
            tenant_id=tenant_id,
            name=hint.name or hint.email or hint.external_id,
            email=hint.email,
            source_type=hint.source_type,
            source_id=hint.external_id,
            member_principal_ids=[],
            member_group_ids=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        
        await self.repo.create_group(group)
        logger.info(f"Created new group {group.id} for hint {hint}")
        return group
    
    async def _expand_group_membership(
        self, entries: List[ACLEntry], tenant_id: UUID
    ) -> List[ACLEntry]:
        """
        Expand group membership to individual principal entries.
        
        For every ACLEntry with a group_id, recursively expand members
        (cycle-safe) and create additional entries.
        """
        expanded: List[ACLEntry] = []
        
        for entry in entries:
            if not entry.group_id:
                continue
            
            # Get group
            group = await self.repo.get_group(entry.group_id, tenant_id)
            if not group:
                logger.warning(f"Group {entry.group_id} not found for expansion")
                continue
            
            # Expand members (cycle-safe)
            member_principal_ids = await self._expand_group_members_safe(
                group, tenant_id, visited=set()
            )
            
            for principal_id in member_principal_ids:
                expanded_entry = ACLEntry(
                    document_id=entry.document_id,
                    principal_id=principal_id,
                    group_id=None,
                    permission=entry.permission,
                    granted_via="group_membership",
                    source_container_id=entry.source_container_id,
                    is_deny=entry.is_deny,
                    source_type=entry.source_type,
                    tenant_id=tenant_id,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                expanded.append(expanded_entry)
        
        return expanded
    
    async def _expand_group_members_safe(
        self, group: Group, tenant_id: UUID, visited: Set[UUID]
    ) -> List[UUID]:
        """
        Recursively expand group membership (cycle-safe).
        
        Args:
            group: Group to expand
            tenant_id: Tenant ID
            visited: Set of already-visited group IDs (cycle detection)
            
        Returns:
            List of principal IDs
        """
        if group.id in visited:
            logger.warning(f"Group membership cycle detected at group {group.id}")
            return []
        
        visited.add(group.id)
        principal_ids = list(group.member_principal_ids)
        
        # Recursively expand nested groups
        for nested_group_id in group.member_group_ids:
            nested_group = await self.repo.get_group(nested_group_id, tenant_id)
            if not nested_group:
                continue
            
            nested_principals = await self._expand_group_members_safe(
                nested_group, tenant_id, visited
            )
            principal_ids.extend(nested_principals)
        
        return principal_ids
    
    def _apply_deny_overrides(self, entries: List[ACLEntry]) -> List[ACLEntry]:
        """
        Apply deny-override logic and deduplicate.
        
        A principal with both allow and deny entries keeps only the deny.
        Deduplicate by (document_id, principal_id, permission) keeping highest privilege.
        """
        # Track deny entries
        deny_keys: Set[Tuple[str, UUID]] = set()
        for entry in entries:
            if entry.is_deny and entry.principal_id:
                deny_keys.add((entry.document_id, entry.principal_id))
        
        # Filter out allows that have denies
        filtered: List[ACLEntry] = []
        for entry in entries:
            if entry.principal_id:
                key = (entry.document_id, entry.principal_id)
                if key in deny_keys and not entry.is_deny:
                    # Skip this allow — deny wins
                    continue
            
            filtered.append(entry)
        
        # Deduplicate: keep highest permission per (document_id, principal_id)
        # Use a dict to track best entry per key
        best: Dict[Tuple[str, UUID | None], ACLEntry] = {}
        
        for entry in filtered:
            key = (entry.document_id, entry.principal_id)
            
            if key not in best:
                best[key] = entry
            else:
                # Compare permission levels (OWNER > DELETE > WRITE > READ > NONE)
                current_level = self._permission_rank(entry.permission)
                best_level = self._permission_rank(best[key].permission)
                
                if current_level > best_level:
                    best[key] = entry
        
        return list(best.values())
    
    def _permission_rank(self, level: PermissionLevel) -> int:
        """Return numeric rank for permission level (higher = more privilege)."""
        ranks = {
            PermissionLevel.NONE: 0,
            PermissionLevel.READ: 1,
            PermissionLevel.WRITE: 2,
            PermissionLevel.DELETE: 3,
            PermissionLevel.OWNER: 4,
        }
        return ranks.get(level, 0)
