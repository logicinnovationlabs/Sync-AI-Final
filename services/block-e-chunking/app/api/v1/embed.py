"""
Embedding API endpoints

POST /embed - enqueue embedding for chunk IDs or document ID
POST /reembed - force re-embedding for tenant and/or model version
GET /embed/jobs/{job_id} - poll job status

Authentication: Uses Block A's JWT-based scope enforcement middleware.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid
import hashlib

from app.models.embedding_job import EmbeddingJob, JobStatus
from app.models.chunk_record import ChunkRecord
from app.config import settings


router = APIRouter()
security = HTTPBearer()


# Request/Response Models
class EmbedRequest(BaseModel):
    """Request to enqueue embedding for chunks or a document."""
    
    chunk_ids: Optional[List[str]] = Field(None, description="List of chunk IDs to embed")
    document_id: Optional[str] = Field(None, description="Document ID to embed all chunks for")
    model_version: Optional[str] = Field(None, description="Model version to use (defaults to current)")
    
    @validator('chunk_ids', 'document_id')
    def validate_target(cls, v, values):
        """Ensure either chunk_ids or document_id is provided, not both."""
        if 'chunk_ids' in values and values['chunk_ids'] is not None and v is not None:
            raise ValueError("Provide either chunk_ids or document_id, not both")
        if 'chunk_ids' not in values or values['chunk_ids'] is None:
            if v is None:
                raise ValueError("Either chunk_ids or document_id must be provided")
        return v


class ReembedRequest(BaseModel):
    """Request to force re-embedding."""
    
    model_version: Optional[str] = Field(None, description="Target model version (if not specified, uses current)")
    document_id: Optional[str] = Field(None, description="Specific document to re-embed (optional)")
    force_all: bool = Field(False, description="Re-embed all chunks for tenant regardless of current version")


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
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None


class EmbedResponse(BaseModel):
    """Response for embed/reembed requests."""
    
    job_id: str
    status: str
    chunks_targeted: int
    message: str


# Block A-style JWT authentication dependencies
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """
    Dependency to get the current authenticated user from JWT.
    
    CRITICAL SECURITY WARNING: This implementation does NOT verify JWT signatures.
    It only decodes the JWT payload without cryptographic verification.
    This means anyone can construct a fake JWT with arbitrary tenant_id claims.
    
    This is a STUB for development only. Before production use, this MUST be replaced
    with Block A's actual token_service.validate_token() which performs signature
    verification against Block A's signing key/JWKS.
    
    Returns:
        Dict with token payload (contains tenant_id, principal_id, scopes, etc.).
        
    Raises:
        HTTPException 401 if token is invalid.
    """
    token = credentials.credentials
    
    # SECURITY: This does NOT verify signatures - DO NOT USE IN PRODUCTION
    # TODO: Replace with Block A's actual token_service.validate_token()
    if not token or len(token) < 10:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Stub: decode JWT payload WITHOUT signature verification
    # This is insecure - anyone can forge a JWT with arbitrary claims
    try:
        import base64
        import json
        
        try:
            # Decode JWT payload (NO SIGNATURE VERIFICATION)
            parts = token.split('.')
            if len(parts) == 3:
                payload = parts[1]
                payload += '=' * (4 - len(payload) % 4)
                decoded = base64.urlsafe_b64decode(payload)
                token_data = json.loads(decoded)
                return token_data
        except:
            pass
        
        # Fallback: mock payload for development
        return {
            "tenant_id": "default_tenant",
            "principal_id": "user_001",
            "scopes": ["embed.write", "embed.read"],
            "exp": 9999999999
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


async def get_tenant(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> str:
    """
    Dependency to extract tenant_id from the current user's JWT.
    
    Returns:
        Tenant ID string.
        
    Raises:
        HTTPException 401 if tenant_id is missing.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")
    return tenant_id


def require_scope(required_scope: str):
    """
    Factory function to create a scope-checking dependency.
    
    This mirrors Block A's require_scope dependency pattern.
    
    Args:
        required_scope: Scope name (e.g., 'embed.write')
        
    Returns:
        FastAPI dependency function.
    """
    async def scope_checker(current_user: Dict[str, Any] = Depends(get_current_user)):
        scopes = current_user.get("scopes", [])
        if required_scope not in scopes:
            raise HTTPException(
                status_code=403,
                detail=f"Missing required scope: {required_scope}",
            )
        return current_user
    
    return scope_checker


@router.post("/embed", response_model=EmbedResponse, dependencies=[Depends(require_scope("embed.write"))])
async def enqueue_embedding(
    request: EmbedRequest,
    tenant_id: str = Depends(get_tenant)
):
    """
    Enqueue embedding for a given set of chunk IDs or a document ID.
    
    This endpoint triggers the embedding pipeline for specified chunks.
    The job is processed asynchronously by the Celery worker.
    
    Authentication: Requires JWT with 'embed.write' scope.
    
    Args:
        request: Embed request with chunk_ids or document_id
        tenant_id: Authenticated tenant ID (from JWT)
    
    Returns:
        Job ID and status information
    """
    # Generate job ID
    job_id = hashlib.sha256(f"{tenant_id}_{uuid.uuid4()}_{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()
    
    # Determine target chunks
    chunks_targeted = 0
    if request.chunk_ids:
        chunks_targeted = len(request.chunk_ids)
    elif request.document_id:
        # In a real implementation, we would query chunk_records to count chunks for this document
        # For now, we'll set a placeholder
        chunks_targeted = 0  # Would be: SELECT COUNT(*) FROM chunk_records WHERE document_id = ?
    
    # Determine model version
    model_version = request.model_version or settings.embedding_model_version
    
    # Create embedding job record
    # Note: In a real implementation, this would use AsyncSession to write to the database
    # For now, we return a mock response
    
    # Enqueue to Celery would happen here
    # embedding_task.delay(job_id, tenant_id, request.chunk_ids, request.document_id, model_version)
    
    return EmbedResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        chunks_targeted=chunks_targeted,
        message=f"Embedding job queued for {chunks_targeted} chunks"
    )


@router.post("/reembed", response_model=EmbedResponse, dependencies=[Depends(require_scope("embed.write"))])
async def enqueue_reembedding(
    request: ReembedRequest,
    tenant_id: str = Depends(get_tenant)
):
    """
    Force re-embedding for a tenant and/or model version.
    
    This endpoint triggers re-embedding of chunks, typically used when:
    - The embedding model version is bumped
    - A specific document needs to be re-processed
    - All chunks for a tenant need to be re-embedded (force_all=True)
    
    Authentication: Requires JWT with 'embed.write' scope.
    
    Args:
        request: Reembed request with optional filters
        tenant_id: Authenticated tenant ID (from JWT)
    
    Returns:
        Job ID and status information
    """
    # Generate job ID
    job_id = hashlib.sha256(f"{tenant_id}_reembed_{uuid.uuid4()}_{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()
    
    # Determine target chunks
    chunks_targeted = 0
    
    if request.force_all:
        # In a real implementation, count all chunks for tenant
        # chunks_targeted = SELECT COUNT(*) FROM chunk_records WHERE tenant_id = ? AND deleted_at IS NULL
        chunks_targeted = 0  # Placeholder
    elif request.document_id:
        # Count chunks for specific document
        # chunks_targeted = SELECT COUNT(*) FROM chunk_records WHERE tenant_id = ? AND document_id = ? AND deleted_at IS NULL
        chunks_targeted = 0  # Placeholder
    else:
        # Re-embed chunks with different model version
        # chunks_targeted = SELECT COUNT(*) FROM chunk_records WHERE tenant_id = ? AND embedding_model_version != ? AND deleted_at IS NULL
        chunks_targeted = 0  # Placeholder
    
    # Determine model version
    model_version = request.model_version or settings.embedding_model_version
    
    # Create embedding job record
    # Note: In a real implementation, this would use AsyncSession to write to the database
    # For now, we return a mock response
    
    # Enqueue to Celery would happen here
    # reembed_task.delay(job_id, tenant_id, model_version, request.document_id, request.force_all)
    
    return EmbedResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        chunks_targeted=chunks_targeted,
        message=f"Re-embedding job queued for {chunks_targeted} chunks"
    )


@router.get("/embed/jobs/{job_id}", response_model=JobResponse, dependencies=[Depends(require_scope("embed.read"))])
async def get_job_status(
    job_id: str,
    tenant_id: str = Depends(get_tenant)
):
    """
    Poll job status for an embedding or re-embedding job.
    
    This endpoint returns the current status of an embedding job,
    including progress (chunks_completed vs chunks_targeted).
    
    Authentication: Requires JWT with 'embed.read' scope.
    
    Args:
        job_id: The job ID to query
        tenant_id: Authenticated tenant ID (from JWT)
    
    Returns:
        Job status and progress information
    """
    # In a real implementation, we would query the embedding_jobs table
    # job = await session.get(EmbeddingJob, job_id)
    # if not job:
    #     raise HTTPException(status_code=404, detail="Job not found")
    # if job.tenant_id != tenant_id:
    #     raise HTTPException(status_code=403, detail="Access denied: job belongs to different tenant")
    
    # For now, return a mock response
    return JobResponse(
        job_id=job_id,
        tenant_id=tenant_id,
        status=JobStatus.PENDING,
        chunks_targeted=0,
        chunks_completed=0,
        model_version=settings.embedding_model_version,
        created_at=datetime.now(timezone.utc),
        started_at=None,
        completed_at=None,
        error=None,
        document_id=None,
        chunk_id=None
    )
