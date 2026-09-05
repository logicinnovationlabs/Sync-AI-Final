"""Admin access override enforcement service.

Provides query-time enforcement of admin-set allow/deny overrides for
per-document access control. This is layered in front of the existing
ACL compile pipeline as an additive check.
"""

from __future__ import annotations

import logging
from typing import Optional, Set, Union
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_access_override import AdminAccessOverride

logger = logging.getLogger(__name__)


class AccessOverrideService:
    """
    Service for checking and enforcing admin access overrides at query time.
    
    Enforcement order (per requirements):
    1. Check admin_access_overrides for (document, target_user) pair first
    2. If deny → exclude regardless of underlying ACL
    3. If allow → include (tenant boundary already validated at set time)
    4. If no override → fall through to existing ACL compile logic
    """
    
    async def get_override(
        self,
        tenant_id: UUID,
        document_id: str,
        target_user_id: UUID,
        db_session: AsyncSession,
    ) -> Optional[str]:
        """
        Get the access override for a specific (document, user) pair.
        
        Args:
            tenant_id: Tenant ID for scoping
            document_id: Document ID to check
            target_user_id: User principal ID to check
            db_session: Database session
            
        Returns:
            "allow", "deny", or None if no override exists
        """
        result = await db_session.execute(
            select(AdminAccessOverride.access)
            .where(
                AdminAccessOverride.tenant_id == tenant_id,
                AdminAccessOverride.document_id == document_id,
                AdminAccessOverride.target_user_id == target_user_id,
            )
        )
        override = result.scalar_one_or_none()
        return override
    
    async def get_denied_document_ids(
        self,
        tenant_id: UUID,
        target_user_id: UUID,
        db_session: AsyncSession,
    ) -> Set[str]:
        """
        Get all document IDs that have a deny override for the target user.
        
        This is useful for batch filtering in search results.
        
        Args:
            tenant_id: Tenant ID for scoping
            target_user_id: User principal ID to check
            db_session: Database session
            
        Returns:
            Set of document IDs with deny overrides
        """
        result = await db_session.execute(
            select(AdminAccessOverride.document_id)
            .where(
                AdminAccessOverride.tenant_id == tenant_id,
                AdminAccessOverride.target_user_id == target_user_id,
                AdminAccessOverride.access == "deny",
            )
        )
        denied_ids = {row[0] for row in result.fetchall()}
        return denied_ids

    async def load_denied_ids_for_caller(
        self,
        current_user: dict,
        tenant_id: Union[str, UUID],
        db_session: AsyncSession,
    ) -> Set[str]:
        """Load deny overrides for search. Fail closed (503) if lookup cannot complete."""
        try:
            user_principal_id = UUID(str(current_user.get("sub")))
            tenant_uuid = UUID(str(tenant_id))
            return await self.get_denied_document_ids(
                tenant_uuid, user_principal_id, db_session
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "Failed to fetch admin deny overrides tenant=%s user=%s",
                tenant_id,
                current_user.get("sub"),
            )
            raise HTTPException(
                status_code=503,
                detail="Access control unavailable",
            ) from exc
    
    async def should_exclude_document(
        self,
        tenant_id: UUID,
        document_id: str,
        target_user_id: UUID,
        db_session: AsyncSession,
    ) -> bool:
        """
        Check if a document should be excluded for the target user based on overrides.
        
        This is the main enforcement point - returns True if deny override exists,
        False otherwise (allow override or no override falls through to ACL).
        
        Args:
            tenant_id: Tenant ID for scoping
            document_id: Document ID to check
            target_user_id: User principal ID to check
            db_session: Database session
            
        Returns:
            True if document should be excluded (deny override), False otherwise
        """
        override = await self.get_override(tenant_id, document_id, target_user_id, db_session)
        
        # Deny override → exclude regardless of ACL
        if override == "deny":
            return True
        
        # Allow override or no override → fall through to ACL
        return False


# Global service instance
access_override_service = AccessOverrideService()
