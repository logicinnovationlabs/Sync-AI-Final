"""
ACL debug/manual endpoint.

GET /acl/{document_id} - get ACL entries for a document
"""

import logging
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List

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
    tenant_id: UUID = Query(..., description="Tenant ID for scoping"),
):
    """
    Get ACL entries for a document (debug/manual endpoint).
    
    Tenant-scoped — only returns entries for the specified tenant.
    
    Args:
        document_id: Document ID
        tenant_id: Tenant ID for scoping
        
    Returns:
        GetACLResponse with ACL entries
    """
    try:
        # Initialize repo
        canonical_repo = CanonicalRepo(use_memory=True)
        
        # Get entries
        entries = await canonical_repo.get_acl_entries(document_id)
        
        # Filter by tenant
        entries = [e for e in entries if e.tenant_id == tenant_id]
        
        return GetACLResponse(
            document_id=document_id,
            tenant_id=tenant_id,
            entries=entries,
        )
    
    except Exception as e:
        logger.error(f"ACL retrieval failed for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
