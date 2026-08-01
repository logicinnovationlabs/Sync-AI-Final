"""
SCIM sync service: idempotent user/group provisioning.

Critical for Signoff A3: principal_id must be identical across sync runs (zero drift).
Uses UUIDv5(NAMESPACE, idp_subject) for deterministic principal_id generation.
"""

from typing import List, Dict, Any
from uuid import UUID, uuid5, NAMESPACE_DNS
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.group import Group, GroupMembership
from app.core.exceptions import SCIMSyncError


# Namespace for principal_id generation (fixed for deterministic UUIDs)
PRINCIPAL_ID_NAMESPACE = uuid5(NAMESPACE_DNS, "snyq-platform.principals")


class SCIMSyncService:
    """
    SCIM 2.0 sync service for user and group provisioning.
    
    Implements idempotent sync via deterministic principal_id = uuid5(NAMESPACE, idp_subject).
    This ensures A3: running sync 3x produces identical principal_id values.
    """

    async def sync_users(
        self,
        scim_users: List[Dict[str, Any]],
        tenant_id: UUID,
        db_session: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Sync users from SCIM feed.
        
        Args:
            scim_users: List of SCIM user objects
            tenant_id: Tenant UUID
            db_session: Database session (tenant DB)
            
        Returns:
            Dict with sync stats (created, updated, unchanged).
        """
        stats = {"created": 0, "updated": 0, "unchanged": 0}
        
        for scim_user in scim_users:
            idp_subject = scim_user.get("id")
            if not idp_subject:
                continue
            
            # A3: Deterministic principal_id via uuid5
            principal_id = uuid5(PRINCIPAL_ID_NAMESPACE, idp_subject)
            
            email = scim_user.get("emails", [{}])[0].get("value", "")
            display_name = scim_user.get("displayName", scim_user.get("userName", ""))
            
            # Check if user exists
            stmt = select(User).where(User.principal_id == principal_id)
            result = await db_session.execute(stmt)
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                # Update if changed
                if existing_user.email != email or existing_user.display_name != display_name:
                    existing_user.email = email
                    existing_user.display_name = display_name
                    existing_user.source_profiles = scim_user
                    stats["updated"] += 1
                else:
                    stats["unchanged"] += 1
            else:
                # Create new user
                new_user = User(
                    principal_id=principal_id,
                    tenant_id=tenant_id,
                    idp_subject=idp_subject,
                    email=email,
                    display_name=display_name,
                    source_profiles=scim_user,
                    status="active",
                )
                db_session.add(new_user)
                stats["created"] += 1
        
        await db_session.commit()
        return stats

    async def sync_groups(
        self,
        scim_groups: List[Dict[str, Any]],
        tenant_id: UUID,
        db_session: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Sync groups from SCIM feed.
        
        Args:
            scim_groups: List of SCIM group objects
            tenant_id: Tenant UUID
            db_session: Database session (tenant DB)
            
        Returns:
            Dict with sync stats.
        """
        stats = {"created": 0, "updated": 0, "unchanged": 0, "membership_changes": 0}
        
        for scim_group in scim_groups:
            source_group_key = scim_group.get("id")
            if not source_group_key:
                continue
            
            display_name = scim_group.get("displayName", "")
            members = scim_group.get("members", [])
            
            # Check if group exists
            stmt = select(Group).where(
                Group.tenant_id == tenant_id,
                Group.source_group_key == source_group_key,
            )
            result = await db_session.execute(stmt)
            existing_group = result.scalar_one_or_none()
            
            if existing_group:
                # Check membership changes
                membership_changed = await self._update_group_membership(
                    existing_group.group_id, members, tenant_id, db_session
                )
                if membership_changed:
                    existing_group.sync_version += 1
                    existing_group.last_membership_update = datetime.now(timezone.utc)
                    stats["membership_changes"] += 1
                stats["updated"] += 1
            else:
                # Create new group
                new_group = Group(
                    tenant_id=tenant_id,
                    group_type="security",
                    display_name=display_name,
                    source_group_key=source_group_key,
                    sync_version=1,
                    last_membership_update=datetime.now(timezone.utc),
                )
                db_session.add(new_group)
                await db_session.flush()
                
                # Add members
                await self._update_group_membership(
                    new_group.group_id, members, tenant_id, db_session
                )
                stats["created"] += 1
        
        await db_session.commit()
        return stats

    async def _update_group_membership(
        self,
        group_id: UUID,
        members: List[Dict[str, Any]],
        tenant_id: UUID,
        db_session: AsyncSession,
    ) -> bool:
        """
        Update group membership (internal helper).
        
        Returns:
            True if membership changed, False otherwise.
        """
        # Get existing memberships
        stmt = select(GroupMembership).where(GroupMembership.group_id == group_id)
        result = await db_session.execute(stmt)
        existing_memberships = {m.principal_id for m in result.scalars().all()}
        
        # Build new membership set
        new_memberships = set()
        for member in members:
            idp_subject = member.get("value")
            if idp_subject:
                principal_id = uuid5(PRINCIPAL_ID_NAMESPACE, idp_subject)
                new_memberships.add(principal_id)
        
        # Detect changes
        to_add = new_memberships - existing_memberships
        to_remove = existing_memberships - new_memberships
        
        if not to_add and not to_remove:
            return False
        
        # Remove old memberships
        if to_remove:
            delete_stmt = select(GroupMembership).where(
                GroupMembership.group_id == group_id,
                GroupMembership.principal_id.in_(to_remove),
            )
            result = await db_session.execute(delete_stmt)
            for membership in result.scalars().all():
                await db_session.delete(membership)
        
        # Add new memberships
        for principal_id in to_add:
            new_membership = GroupMembership(
                group_id=group_id,
                principal_id=principal_id,
                tenant_id=tenant_id,
            )
            db_session.add(new_membership)
        
        return True


# Global SCIM sync service instance
scim_sync_service = SCIMSyncService()
