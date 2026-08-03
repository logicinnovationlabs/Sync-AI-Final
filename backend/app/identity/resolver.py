"""
Identity resolver for mapping raw hints to stable principal IDs.

Resolution is tenant-scoped and uses a DB-level uniqueness constraint to prevent
race-condition duplicate Principal rows.
"""

import logging
from typing import List, Optional
from uuid import uuid4, UUID
from datetime import datetime, timezone
from email_validator import validate_email, EmailNotValidError

from app.core.models import IdentityHint, ResolvedIdentity, Principal

logger = logging.getLogger(__name__)


class IdentityResolver:
    """
    Resolves identity hints to stable principal IDs.
    
    Uses matchers in priority order (email > username) and creates new
    Principal rows for previously unseen identities.
    
    Concurrency-safe via DB-level uniqueness constraint on (tenant_id, lower(email)).
    """
    
    def __init__(self, matchers: List, canonical_repo):
        """
        Initialize identity resolver.
        
        Args:
            matchers: List of matcher instances (e.g., [EmailMatcher(), UsernameMatcher()])
            canonical_repo: Repository for Principal persistence
        """
        self.matchers = matchers
        self.repo = canonical_repo
    
    async def resolve(self, hint: IdentityHint, tenant_id: UUID) -> ResolvedIdentity:
        """
        Resolve an identity hint to a principal.
        
        Process:
        1. Normalize the hint's email (lowercase, strip whitespace)
        2. Look up existing Principal by email (exact, case-insensitive, tenant-scoped)
        3. If found, update source_identities and return with confidence 1.0
        4. If not found and email is present, create new Principal
        5. If email is absent, fall back to username matcher (source-scoped only)
        
        Args:
            hint: Raw identity hint from source
            tenant_id: Tenant ID (scopes resolution)
            
        Returns:
            ResolvedIdentity with principal and match metadata
        """
        # Normalize email if present
        normalized_email = self._normalize_email(hint.email) if hint.email else None
        
        # Try email matcher first (highest confidence)
        if normalized_email:
            principal = await self._match_by_email(normalized_email, tenant_id, hint)
            if principal:
                return ResolvedIdentity(
                    principal_id=principal.id,
                    principal=principal,
                    confidence=1.0,
                    matched_on="email",
                )
        
        # Try username matchers (source-scoped only, lower confidence)
        if hint.username:
            for matcher in self.matchers:
                if hasattr(matcher, "match_by_username"):
                    principal = await matcher.match_by_username(
                        hint.username, hint.source_type, tenant_id, self.repo
                    )
                    if principal:
                        # Update source_identities
                        await self._update_source_identity(principal, hint)
                        return ResolvedIdentity(
                            principal_id=principal.id,
                            principal=principal,
                            confidence=0.8,
                            matched_on="username",
                        )
        
        # No match found — create new principal if email is present
        if normalized_email:
            principal = await self._create_principal(normalized_email, tenant_id, hint)
            return ResolvedIdentity(
                principal_id=principal.id,
                principal=principal,
                confidence=1.0,
                matched_on="new",
            )
        
        # No email and no username match — cannot create principal
        # Return a special "unresolved" principal (or raise error)
        logger.error(
            f"Cannot resolve identity hint with no email: "
            f"source={hint.source_type}, external_id={hint.external_id}"
        )
        raise ValueError(f"Cannot resolve identity hint with no email: {hint}")
    
    async def _match_by_email(
        self, normalized_email: str, tenant_id: UUID, hint: IdentityHint
    ) -> Optional[Principal]:
        """
        Match principal by normalized email.
        
        Tenant-scoped, case-insensitive exact match.
        Updates source_identities if found.
        """
        principal = await self.repo.get_principal_by_email(normalized_email, tenant_id)
        
        if principal:
            # Update source_identities if not already present
            await self._update_source_identity(principal, hint)
        
        return principal
    
    async def _update_source_identity(self, principal: Principal, hint: IdentityHint) -> None:
        """
        Add source_identities entry if not already present.
        """
        if hint.source_type not in principal.source_identities:
            principal.source_identities[hint.source_type] = hint.external_id
            principal.updated_at = datetime.now(timezone.utc)
            await self.repo.update_principal(principal)
            logger.info(
                f"Updated principal {principal.id} with source identity: "
                f"{hint.source_type}={hint.external_id}"
            )
    
    async def _create_principal(
        self, normalized_email: str, tenant_id: UUID, hint: IdentityHint
    ) -> Principal:
        """
        Create a new principal.
        
        Handles race condition via DB uniqueness constraint on (tenant_id, lower(email)).
        If constraint is violated, re-query and return the winner.
        """
        principal = Principal(
            id=uuid4(),
            tenant_id=tenant_id,
            email=normalized_email,
            name=hint.name,
            source_identities={hint.source_type: hint.external_id},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        
        try:
            await self.repo.create_principal(principal)
            logger.info(
                f"Created new principal {principal.id} for email {normalized_email} "
                f"in tenant {tenant_id}"
            )
            return principal
        except Exception as e:
            # Check if uniqueness constraint violation
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                logger.info(
                    f"Race condition detected creating principal for {normalized_email}, "
                    f"re-querying..."
                )
                # Re-query to get the winner
                existing = await self.repo.get_principal_by_email(normalized_email, tenant_id)
                if existing:
                    # Update source_identities
                    await self._update_source_identity(existing, hint)
                    return existing
            
            # Other error — re-raise
            logger.error(f"Failed to create principal: {e}")
            raise
    
    def _normalize_email(self, email: Optional[str]) -> Optional[str]:
        """
        Normalize email address.
        
        Lowercase and strip whitespace. Do NOT apply Gmail-specific
        dot-insensitivity or plus-addressing folding globally — that's
        Gmail-specific and would incorrectly merge different people on
        sources that don't share that convention.
        
        Args:
            email: Raw email address
            
        Returns:
            Normalized email (lowercase, stripped) or None
        """
        if not email:
            return None
        
        email = email.strip().lower()
        
        # Validate format
        try:
            validate_email(email, check_deliverability=False)
        except EmailNotValidError as e:
            logger.warning(f"Invalid email format '{email}': {e}")
            return None
        
        return email
