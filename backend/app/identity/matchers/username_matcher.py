"""
Username-based identity matcher.

Fallback matcher when no email is present.
Source-scoped only — never merges usernames across sources.
"""

import logging
from typing import Optional
from uuid import UUID
from app.core.models import Principal

logger = logging.getLogger(__name__)


class UsernameMatcher:
    """
    Matcher for username-based identity resolution.
    
    Matches on (tenant_id, source_type, username) — never cross-source.
    Lower confidence than email matching.
    """
    
    async def match_by_username(
        self, username: str, source_type: str, tenant_id: UUID, repo
    ) -> Optional[Principal]:
        """
        Find principal by username within a specific source type.
        
        Never matches across sources — usernames are not globally unique.
        
        Args:
            username: Username/handle
            source_type: Source type identifier
            tenant_id: Tenant ID for scoping
            repo: Canonical repository for Principal lookup
            
        Returns:
            Matching Principal or None
        """
        # Look up by source_identities mapping
        # NOTE: This requires the repo to support querying by source_identities,
        # which we'll add to canonical_repo
        return await repo.get_principal_by_source_identity(
            source_type, username, tenant_id
        )
