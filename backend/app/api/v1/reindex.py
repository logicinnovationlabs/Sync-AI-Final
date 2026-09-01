"""Reindexing API for fixing ACL terms on existing documents.

This endpoint allows triggering a reindex of all documents for a tenant/source
to update ACL terms with the corrected unified format. Required after the
ACL term generation fix to ensure existing documents become queryable.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user, require_scope
from app.workers.tasks import reindex_connector_documents_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["reindex"])


class ReindexRequest(BaseModel):
    """Request to reindex documents for a connector source."""
    source_type: str
    reason: str = "acl_fix"


class ReindexResponse(BaseModel):
    """Response from reindex trigger."""
    status: str
    task_id: str
    tenant_id: str
    source_type: str
    message: str


@router.post("/reindex/connector", response_model=ReindexResponse)
async def trigger_reindex(
    body: ReindexRequest,
    current_user: Dict[str, Any] = Depends(require_scope("connectors.write")),
):
    """
    Trigger reindexing of all documents for a connector source.
    
    This rebuilds ACL terms using the unified ACL term generator to ensure
    documents become visible in searches. Required after fixing the ACL
    mismatch between indexing and querying.
    
    Args:
        body: Reindex request with source_type and reason
        current_user: Authenticated user from JWT
        
    Returns:
        Task information for the background reindex job
        
    Raises:
        HTTPException: If tenant_id is missing or invalid
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")
    
    user_id = str(
        current_user.get("principal_id")
        or current_user.get("user_id")
        or current_user.get("sub")
        or ""
    )
    
    logger.info(
        "Reindex triggered by user tenant=%s user=%s source=%s reason=%s",
        tenant_id,
        user_id,
        body.source_type,
        body.reason,
    )
    
    # Queue the reindex task
    task_result = reindex_connector_documents_task.delay(
        tenant_id=tenant_id,
        source_type=body.source_type,
        user_id=user_id,
    )
    
    return ReindexResponse(
        status="queued",
        task_id=task_result.id,
        tenant_id=tenant_id,
        source_type=body.source_type,
        message=f"Reindexing {body.source_type} documents with corrected ACL terms",
    )


@router.get("/reindex/health")
async def reindex_health():
    """Health check for reindex API."""
    return {"status": "ok", "service": "reindex_api"}
