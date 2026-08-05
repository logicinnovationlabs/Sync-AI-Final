"""
Identity resolution debug/manual endpoint.

POST /identity/resolve - manually resolve an identity hint
"""

import logging
from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.models import IdentityHint, ResolvedIdentity
from app.identity.resolver import IdentityResolver
from app.identity.matchers.email_matcher import EmailMatcher
from app.identity.matchers.username_matcher import UsernameMatcher
from app.storage.canonical_repo import CanonicalRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/identity", tags=["identity"])


class ResolveIdentityRequest(BaseModel):
    """Request body for identity resolution."""
    tenant_id: UUID
    hint: IdentityHint


class ResolveIdentityResponse(BaseModel):
    """Response body for identity resolution."""
    resolved: ResolvedIdentity


@router.post("/resolve", response_model=ResolveIdentityResponse)
async def resolve_identity(request: ResolveIdentityRequest):
    """
    Manually resolve an identity hint (debug/manual endpoint).
    
    Args:
        request: ResolveIdentityRequest with tenant_id and hint
        
    Returns:
        ResolvedIdentity with principal and match metadata
    """
    try:
        # Initialize resolver
        canonical_repo = CanonicalRepo(use_memory=True)
        matchers = [EmailMatcher(), UsernameMatcher()]
        resolver = IdentityResolver(matchers, canonical_repo)
        
        # Resolve
        resolved = await resolver.resolve(request.hint, request.tenant_id)
        
        return ResolveIdentityResponse(resolved=resolved)
    
    except Exception as e:
        logger.error(f"Identity resolution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
