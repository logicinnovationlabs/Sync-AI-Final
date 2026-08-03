"""
Email-based identity matcher.

Exact match on normalized (lowercased, whitespace-stripped) email.
Tenant-scoped — never merges across tenants.
"""

import logging
from typing import Optional
from uuid import UUID
from app.core.models import Principal

logger = logging.getLogger(__name__)


class EmailMatcher:
    """
    Matcher for email-based identity resolution.
    
    Exact match on normalized email, scoped to tenant_id.
    """
    
    async def match_by_email(
        self, email: str, tenant_id: UUID, repo
    ) -> Optional[Principal]:
        """
        Find principal by exact email match.
        
        Args:
            email: Normalized email address (already lowercased/stripped)
            tenant_id: Tenant ID for scoping
            repo: Canonical repository for Principal lookup
            
        Returns:
            Matching Principal or None
        """
        return await repo.get_principal_by_email(email, tenant_id)
