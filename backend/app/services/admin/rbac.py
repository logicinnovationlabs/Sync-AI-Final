"""RBAC service: role hierarchy and permission checking for owner/admin/member/viewer.

Provides centralized permission checking to enforce role-based access control invariants:
- Role hierarchy: owner > admin > member > viewer
- No principal can grant a role higher than or equal to their own
- No principal can edit their own role
- Only owner can promote to admin
- Tenant must always have exactly one owner
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.models.user import User


# Role hierarchy: higher number = higher privilege
ROLE_HIERARCHY = {
    "owner": 4,
    "admin": 3,
    "member": 2,
    "viewer": 1,
}


class RBACService:
    """
    Centralized RBAC enforcement service.
    
    All role-based permission checks should go through this service
    to ensure consistent enforcement of invariants.
    """

    def get_role_level(self, role: str) -> int:
        """Get the numeric level of a role for hierarchy comparison."""
        return ROLE_HIERARCHY.get(role, 0)

    def can_grant_role(self, actor_role: str, target_role: str) -> bool:
        """
        Check if an actor with actor_role can grant target_role to someone else.
        
        Rules:
        - No principal can grant a role higher than or equal to their own
        - Only owner can grant admin role (per Decision 2)
        - Only owner can grant owner role (implicit from hierarchy rule)
        
        Returns:
            True if the grant is permitted, False otherwise.
        """
        actor_level = self.get_role_level(actor_role)
        target_level = self.get_role_level(target_role)
        
        # Cannot grant role higher than or equal to own level
        if target_level >= actor_level:
            return False
        
        # Only owner can grant admin role
        if target_role == "admin" and actor_role != "owner":
            return False
        
        return True

    def can_edit_role(self, actor_role: str, target_user_role: str, new_role: str) -> bool:
        """
        Check if an actor can change a user's role to new_role.
        
        This combines can_grant_role with additional checks for demotion.
        """
        # Check if actor can grant the new role
        if not self.can_grant_role(actor_role, new_role):
            return False
        
        # Additional check: actor must be higher than current target role
        # (to prevent lateral moves that shouldn't be allowed)
        actor_level = self.get_role_level(actor_role)
        target_level = self.get_role_level(target_user_role)
        
        if target_level >= actor_level:
            return False
        
        return True

    async def check_sole_owner_protection(
        self,
        tenant_id: UUID,
        target_user_id: UUID,
        db_session: AsyncSession,
    ) -> None:
        """
        Check if the target user is the sole owner of the tenant.
        
        Raises:
            ForbiddenError if the target is the sole owner and the operation
            would leave the tenant with zero owners.
        """
        # Count owners in the tenant
        result = await db_session.execute(
            select(func.count())
            .select_from(User)
            .where(
                User.tenant_id == tenant_id,
                User.role == "owner",
                User.is_active == True,
            )
        )
        owner_count = result.scalar_one()
        
        # If there's only one owner, check if it's the target user
        if owner_count == 1:
            result = await db_session.execute(
                select(User)
                .where(
                    User.principal_id == target_user_id,
                    User.tenant_id == tenant_id,
                    User.role == "owner",
                )
            )
            target_is_owner = result.scalar_one_or_none()
            
            if target_is_owner:
                raise ForbiddenError(
                    "Cannot demote or deactivate the sole owner of a tenant. "
                    "Transfer ownership to another user first."
                )

    async def check_self_role_edit_prevention(
        self,
        actor_id: UUID,
        target_user_id: UUID,
    ) -> None:
        """
        Check if the actor is trying to edit their own role.
        
        Raises:
            ForbiddenError if actor_id == target_user_id.
        """
        if actor_id == target_user_id:
            raise ForbiddenError(
                "Cannot edit your own role. This prevents self-escalation and accidental lockout."
            )

    async def check_role_change_permission(
        self,
        actor: User,
        target_user: User,
        new_role: str,
        db_session: AsyncSession,
    ) -> None:
        """
        Comprehensive check for role change operations.
        
        This consolidates all RBAC invariants for role changes:
        1. Self-role-edit prevention
        2. Sole-owner protection (when demoting/deactivating owner)
        3. Role hierarchy enforcement (can't grant higher/equal roles)
        4. Admin-can't-create-admin enforcement
        
        Raises:
            ForbiddenError if any invariant is violated.
        """
        # Check self-role-edit prevention
        await self.check_self_role_edit_prevention(
            actor.principal_id,
            target_user.principal_id,
        )
        
        # Check if actor can grant the new role
        if not self.can_grant_role(actor.role, new_role):
            raise ForbiddenError(
                f"Users with role '{actor.role}' cannot grant role '{new_role}' to others. "
                f"Only owners can promote users to admin or owner roles."
            )
        
        # Check sole-owner protection if demoting from owner
        if target_user.role == "owner" and new_role != "owner":
            await self.check_sole_owner_protection(
                target_user.tenant_id,
                target_user.principal_id,
                db_session,
            )

    async def check_deactivation_permission(
        self,
        actor: User,
        target_user: User,
        db_session: AsyncSession,
    ) -> None:
        """
        Check if actor can deactivate target_user.
        
        Raises:
            ForbiddenError if actor cannot deactivate the target.
        """
        # Check self-role-edit prevention
        await self.check_self_role_edit_prevention(
            actor.principal_id,
            target_user.principal_id,
        )
        
        # Check role hierarchy: actor must be higher than target
        actor_level = self.get_role_level(actor.role)
        target_level = self.get_role_level(target_user.role)
        
        if target_level >= actor_level:
            raise ForbiddenError(
                f"Users with role '{actor.role}' cannot deactivate users with role '{target_user.role}'."
            )
        
        # Check sole-owner protection
        if target_user.role == "owner":
            await self.check_sole_owner_protection(
                target_user.tenant_id,
                target_user.principal_id,
                db_session,
            )


# Global RBAC service instance
rbac_service = RBACService()
