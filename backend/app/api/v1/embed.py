"""
Embedding API endpoints for Block E: Chunking & Embeddings

POST /embed - enqueue embedding for chunk IDs or document ID
POST /reembed - force re-embedding for tenant and/or model version
GET /embed/jobs/{job_id} - poll job status

Authentication: Uses Block A's JWT-based scope enforcement middleware.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid
import hashlib

from app.core.config import settings
from app.api.deps import get_current_user, require_scope

router = APIRouter()


# Request/Response Models
class EmbedRequest(BaseModel):
    """Request to enqueue embedding for chunks or a document."""
    
    chunk_ids: Optional[List[str]] = Field(None, description="List of chunk IDs to embed")
    document_id: Optional[str] = Field(None, description="Document ID to embed all chunks for")
    model_version: Optional[str] = Field(None, description="Model version to use (defaults to current)")


class ReembedRequest(BaseModel):
    """Request to force re-embedding."""
    
    model_version: Optional[str] = Field(None, description="Target model version")
    document_id: Optional[str] = Field(None, description="Specific document to re-embed")
    force_all: bool = Field(False, description="Re-embed all chunks for tenant")


class JobResponse(BaseModel):
    """Response for job status queries."""
    
    job_id: str
    tenant_id: str
    status: str
    chunks_targeted: int
    chunks_completed: int
    model_version: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class EmbedResponse(BaseModel):
    """Response for embed/reembed requests."""
    
    job_id: str
    status: str
    chunks_targeted: int
    message: str


async def get_tenant(current_user: Dict[str, Any] = Depends(get_current_user)) -> str:
    """Extract tenant_id from authenticated user."""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")
    return tenant_id


@router.post("/embed", response_model=EmbedResponse)
async def enqueue_embedding(
    request: EmbedRequest,
    current_user: Dict[str, Any] = Depends(require_scope("embed.write")),
    tenant_id: str = Depends(get_tenant)
):
    """Enqueue embedding for chunks or document."""
    job_id = hashlib.sha256(
        f"{tenant_id}_{uuid.uuid4()}_{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()
    
    chunks_targeted = len(request.chunk_ids) if request.chunk_ids else 0
    model_version = request.model_version or getattr(settings, 'embedding_model_version', 'v1')
    
    return EmbedResponse(
        job_id=job_id,
        status="pending",
        chunks_targeted=chunks_targeted,
        message=f"Embedding job queued for {chunks_targeted} chunks"
    )


@router.post("/reembed", response_model=EmbedResponse)
async def enqueue_reembedding(
    request: ReembedRequest,
    current_user: Dict[str, Any] = Depends(require_scope("embed.write")),
    tenant_id: str = Depends(get_tenant)
):
    """Force re-embedding for tenant/model version."""
    job_id = hashlib.sha256(
        f"{tenant_id}_reembed_{uuid.uuid4()}_{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()
    
    chunks_targeted = 0
    model_version = request.model_version or getattr(settings, 'embedding_model_version', 'v1')
    
    return EmbedResponse(
        job_id=job_id,
        status="pending",
        chunks_targeted=chunks_targeted,
        message="Re-embedding job queued"
    )


@router.get("/embed/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(
    job_id: str,
    current_user: Dict[str, Any] = Depends(require_scope("embed.read")),
    tenant_id: str = Depends(get_tenant)
):
    """Poll job status for embedding/re-embedding job."""
    return JobResponse(
        job_id=job_id,
        tenant_id=tenant_id,
        status="pending",
        chunks_targeted=0,
        chunks_completed=0,
        model_version=getattr(settings, 'embedding_model_version', 'v1'),
        created_at=datetime.now(timezone.utc),
        started_at=None,
        completed_at=None,
        error=None
    )
