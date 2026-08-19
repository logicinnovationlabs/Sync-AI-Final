"""
Identity resolution debug/manual endpoint.

POST /identity/resolve - manually resolve an identity hint
"""

import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_session
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
async def resolve_identity(
    request: ResolveIdentityRequest,
    current_user: dict = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """
    Manually resolve an identity hint (debug/manual endpoint).

    Requires a JWT whose tenant_id matches the request tenant.
    """
    token_tenant = str(current_user.get("tenant_id") or "")
    if token_tenant != str(request.tenant_id):
        raise HTTPException(status_code=403, detail="Tenant ID mismatch")

    try:
        canonical_repo = CanonicalRepo(use_memory=False, session=db_session)
        matchers = [EmailMatcher(), UsernameMatcher()]
        resolver = IdentityResolver(matchers, canonical_repo)

        resolved = await resolver.resolve(request.hint, request.tenant_id)

        return ResolveIdentityResponse(resolved=resolved)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Identity resolution failed: %s", e)
        raise HTTPException(status_code=500, detail="Identity resolution failed") from e
