"""
ACL debug/manual endpoint.

GET /acl/{document_id} - get ACL entries for a document
"""

import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_session, require_admin
from app.core.models import ACLEntry
from app.storage.canonical_repo import CanonicalRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/acl", tags=["acl"])


class GetACLResponse(BaseModel):
    """Response body for ACL retrieval."""
    document_id: str
    tenant_id: UUID
    entries: List[ACLEntry]


@router.get("/{document_id}", response_model=GetACLResponse)
async def get_acl(
    document_id: str,
    admin: dict = Depends(require_admin),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """
    Get ACL entries for a document.

    Admin-only. Tenant is taken from the JWT — callers cannot query another tenant.
    """
    token_tenant = admin.get("tenant_id")
    if not token_tenant:
        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")
    try:
        tenant_id = UUID(str(token_tenant))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Token tenant_id is malformed")

    try:
        canonical_repo = CanonicalRepo(use_memory=False, session=db_session)

        entries = await canonical_repo.get_acl_entries(document_id)
        entries = [e for e in entries if e.tenant_id == tenant_id]

        return GetACLResponse(
            document_id=document_id,
            tenant_id=tenant_id,
            entries=entries,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("ACL retrieval failed for document %s: %s", document_id, e)
        raise HTTPException(status_code=500, detail="ACL retrieval failed") from e
