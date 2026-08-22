"""Admin view of unmatched Drive/Gmail emails waiting for a users bind."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant, get_tenant_session, require_admin
from app.services.tenant_resolver import TenantRouting
from app.storage.canonical_repo import CanonicalRepo

router = APIRouter(prefix="/pending-identities", tags=["admin-pending-identities"])


class PendingIdentityItem(BaseModel):
    document_id: str
    shared_email: str
    first_seen_at: Optional[datetime] = None


def _as_uuid(value) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


@router.get("", response_model=List[PendingIdentityItem])
async def list_pending_identities(
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """Exact-email unmatched shares. alice@gmail.com ≠ alice+work@gmail.com."""
    _ = admin
    repo = CanonicalRepo(use_memory=False, session=db_session)
    rows = await repo.list_unresolved_pending(_as_uuid(tenant.tenant_id))
    return [PendingIdentityItem(**row) for row in rows]
