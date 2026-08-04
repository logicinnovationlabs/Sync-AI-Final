"""
Component 5: Embedding Job Queue with Tenant Isolation
Celery-based worker that processes embedding jobs with strict tenant isolation.
"""

from celery import Celery
from typing import Dict, Any
import os
import redis
from datetime import datetime, timezone
import struct
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from app.models.chunk_record import ChunkRecord

# Initialize Celery app
celery_app = Celery(
    'embedding_worker',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2')
)

# Initialize Redis for provider call logging
redis_client = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'), decode_responses=True)
PROVIDER_CALL_LOG_KEY = 'embedding:provider_call_log'

# Initialize database engine for updating chunk_records (synchronous for Celery)
# Default to localhost for local development; Docker Compose sets this to postgres hostname
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@localhost:5432/block_e')
# Convert async URL to sync URL for worker
SYNC_DATABASE_URL = DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql://')
db_engine = create_engine(SYNC_DATABASE_URL, echo=False)
SessionLocal = sessionmaker(db_engine, expire_on_commit=False)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)


def validate_tenant_isolation(job_data: Dict[str, Any]) -> str:
    """
    Validate tenant isolation for a job.
    
    CRITICAL TENANT ISOLATION GUARD:
    - This function validates that a job has proper tenant isolation
    - Called before any processing logic
    - Raises AssertionError if isolation is violated
    
    Args:
        job_data: Dictionary containing job data
    
    Returns:
        tenant_id if validation passes
    
    Raises:
        AssertionError: If tenant isolation is violated
    """
    # EXPLICIT CHECK: tenant_id must be present and non-falsy before ANY other logic
    tenant_id = job_data.get('tenant_id')
    if not tenant_id:
        raise AssertionError(
            "TENANT ISOLATION VIOLATION: tenant_id is missing or falsy in job_data. "
            "This is a critical security violation - all jobs must have a valid tenant_id."
        )
    
    chunk_id = job_data.get('chunk_id')
    if not chunk_id:
        raise AssertionError("TENANT ISOLATION VIOLATION: chunk_id missing from job_data")
    
    # Verify this is a single-chunk job (no batching across tenants)
    if 'chunks' in job_data and len(job_data['chunks']) > 1:
        # If batching is used, verify all chunks belong to the same tenant
        chunks = job_data['chunks']
        chunk_tenants = set(chunk.get('tenant_id') for chunk in chunks)
        
        if len(chunk_tenants) > 1:
            raise AssertionError(
                f"TENANT ISOLATION VIOLATION: Batching chunks from multiple tenants: {chunk_tenants}. "
                "This is a hard architectural violation per §28.3."
            )
    
    return tenant_id


@celery_app.task(bind=True)
def embedding_task(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single embedding job.
    
    CRITICAL TENANT ISOLATION GUARD:
    - This task processes exactly ONE chunk from exactly ONE tenant
    - The unit of work is a single job_id, which corresponds to a single chunk_id
    - If any batching optimization is introduced, it MUST batch multiple chunks 
      from the SAME tenant only, never mix tenants in a single provider call
    - This assertion fails loudly if violated
    
    Args:
        job_data: Dictionary containing:
            - job_id: Unique job identifier
            - tenant_id: Tenant identifier (CRITICAL for isolation)
            - chunk_id: Chunk identifier
            - content_text: Text to embed
            - model_version_target: Target embedding model version
    
    Returns:
        Dictionary with embedding result
    
    Raises:
        AssertionError: If tenant isolation is violated
    """
    # Get Celery task ID for logging per v7.0 §2.4
    celery_task_id = self.request.id
    
    # TENANT ISOLATION ASSERTION - Hard-stop item from §0/§1
    tenant_id = validate_tenant_isolation(job_data)
    chunk_id = job_data.get('chunk_id')
    job_id = job_data['job_id']
    document_id = job_data.get('document_id')  # Per v7.0 §2.2: denormalized field for join-check
    
    # Log both IDs explicitly per v7.0 §2.4
    print(f"[TENANT_ISOLATION] Processing job_id={job_id} celery_task_id={celery_task_id} for tenant={tenant_id}, chunk={chunk_id}")
    
    # Log provider call to Redis for E5 verification
    # This is the actual worker-side provider call log that E5 must inspect
    import json
    provider_call_log = {
        'tenant_id': tenant_id,
        'chunk_id': chunk_id,
        'job_id': job_id,
        'celery_task_id': celery_task_id,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
    redis_client.lpush(PROVIDER_CALL_LOG_KEY, json.dumps(provider_call_log))
    print(f"[DIAGNOSTIC] job_id={job_id} celery_task_id={celery_task_id} Logged provider call for chunk_id={chunk_id}")
    
    # Simulate embedding generation (in production, call actual embedding provider)
    # For now, return a mock embedding vector
    embedding_vector = [0.0] * 1536  # Mock 1536-dimensional vector
    embedding_vector[0] = hash(chunk_id) % 100 / 100.0  # Deterministic mock
    
    # Serialize embedding vector to bytes for database storage
    embedding_bytes = struct.pack(f'{len(embedding_vector)}f', *embedding_vector)
    
    # Per v7.0 §2.2: Validate document_id via join-check against chunk_records
    # This is not trusted - it must be verified in the write path
    if document_id:
        session = SessionLocal()
        try:
            # Join-check: verify that document_id in job matches chunk_records.document_id for this chunk_id
            check_result = session.execute(
                select(ChunkRecord.document_id)
                .where(ChunkRecord.chunk_id == chunk_id)
            ).one_or_none()
            
            if check_result is None:
                session.close()
                raise AssertionError(
                    f"[v7.0 §2.2 VIOLATION] Chunk does not exist for chunk_id={chunk_id}. "
                    f"job_id={job_id} celery_task_id={celery_task_id}. "
                    f"Cannot validate document_id join-check."
                )
            
            chunk_document_id = check_result[0]
            if chunk_document_id != document_id:
                session.close()
                raise AssertionError(
                    f"[v7.0 §2.2 VIOLATION] document_id mismatch: job has document_id={document_id} "
                    f"but chunk_records has document_id={chunk_document_id} for chunk_id={chunk_id}. "
                    f"job_id={job_id} celery_task_id={celery_task_id}. "
                    f"This is a data integrity violation - the denormalized field must match the source."
                )
            
            print(f"[DIAGNOSTIC] job_id={job_id} celery_task_id={celery_task_id} document_id join-check passed: {document_id}")
            session.close()
        except Exception as e:
            session.close()
            raise
    
    # Update chunk_records with embedding result (Defect 12 fix - using sync SQLAlchemy)
    print(f"[DIAGNOSTIC] job_id={job_id} celery_task_id={celery_task_id} Updating chunk_record for chunk_id={chunk_id}")
    session = SessionLocal()
    try:
        # [IDEMPOTENCY - v7.0 §4.5 + TOCTOU FIX]: Use atomic conditional UPDATE
        # Single statement with WHERE clause that only matches rows needing update
        # This eliminates TOCTOU race between SELECT and UPDATE
        # rowcount == 0 means "already at target version" (legitimate no-op), not a race
        # rowcount == 0 with row not existing is caught by separate SELECT after
        from sqlalchemy import and_, or_
        
        update_result = session.execute(
            update(ChunkRecord)
            .where(
                and_(
                    ChunkRecord.chunk_id == chunk_id,
                    or_(
                        ChunkRecord.embedding_model_version != job_data['model_version_target'],
                        ChunkRecord.embedding_vector.is_(None)
                    )
                )
            )
            .values(
                embedding_vector=embedding_bytes,
                embedding_model_version=job_data['model_version_target'],
                embedding_timestamp=datetime.utcnow()
            )
        )
        rowcount = update_result.rowcount
        
        if rowcount == 0:
            # rowcount == 0 means either: (a) row doesn't exist, or (b) already at target version
            # Distinguish with a SELECT - this is safe because we're not making a decision based on it
            check_exists = session.execute(
                select(ChunkRecord.chunk_id, ChunkRecord.embedding_model_version, ChunkRecord.embedding_vector)
                .where(ChunkRecord.chunk_id == chunk_id)
            ).one_or_none()
            
            if check_exists is None:
                # Row doesn't exist - genuine failure
                session.rollback()
                raise AssertionError(
                    f"[HARDENING VIOLATION v7.0 §4.6] Chunk row does not exist for chunk_id={chunk_id}. "
                    f"job_id={job_id} celery_task_id={celery_task_id}. "
                    f"Task must fail loudly - cannot embed a non-existent chunk."
                )
            
            current_version, current_vector = check_exists[1], check_exists[2]
            
            # Row exists and is already at target version - legitimate no-op per §4.5
            print(f"[DIAGNOSTIC] job_id={job_id} celery_task_id={celery_task_id} Chunk already at target version {current_version}, skipping UPDATE (idempotent no-op)")
            session.close()
            return {
                'job_id': job_id,
                'celery_task_id': celery_task_id,
                'tenant_id': tenant_id,
                'chunk_id': chunk_id,
                'embedding_vector': None,  # Not regenerated
                'embedding_model_version': current_version,
                'status': 'complete',
                'skipped': True  # Flag to indicate no-op
            }
        
        # rowcount > 0 means UPDATE succeeded
        session.commit()
        print(f"[DIAGNOSTIC] job_id={job_id} celery_task_id={celery_task_id} Committed update for chunk_id={chunk_id}, rowcount={rowcount}")
        
        # Verify the write per v7.0 §4.6
        result = session.execute(
            select(ChunkRecord).where(ChunkRecord.chunk_id == chunk_id)
        )
        chunk = result.scalar_one_or_none()
        if chunk and chunk.embedding_vector is not None:
            print(f"[DIAGNOSTIC] job_id={job_id} celery_task_id={celery_task_id} Verified: chunk_id={chunk_id} has embedding_vector")
        else:
            # [HARDENING - v7.0 §4.6]: Explicit failure on verification failure
            session.rollback()
            raise AssertionError(
                f"[HARDENING VIOLATION v7.0 §4.6] embedding_vector is None after write for chunk_id={chunk_id}. "
                f"job_id={job_id} celery_task_id={celery_task_id}. "
                f"Task must fail loudly, not log ERROR and return success."
            )
    except Exception as e:
        print(f"[DIAGNOSTIC] job_id={job_id} celery_task_id={celery_task_id} ERROR updating chunk_record: {e}")
        session.rollback()
        raise
    finally:
        session.close()
    
    result = {
        'job_id': job_id,
        'celery_task_id': celery_task_id,
        'tenant_id': tenant_id,
        'chunk_id': chunk_id,
        'embedding_vector': embedding_vector,
        'embedding_model_version': job_data['model_version_target'],
        'status': 'complete'
    }
    
    print(f"[TENANT_ISOLATION] Completed job_id={job_id} celery_task_id={celery_task_id} for tenant={tenant_id}")
    
    return result


class EmbeddingJobQueue:
    """
    Manages embedding job queue with tenant isolation enforcement.
    """
    
    def __init__(self, celery_app: Celery):
        self.celery_app = celery_app
    
    def enqueue_job(
        self,
        job_id: str,
        tenant_id: str,
        chunk_id: str,
        document_id: str,  # Per v7.0 §2.2: required for join-check validation
        content_text: str,
        model_version: str
    ) -> str:
        """
        Enqueue a single embedding job.
        
        Args:
            job_id: Unique job identifier
            tenant_id: Tenant identifier
            chunk_id: Chunk identifier
            document_id: Document identifier (per v7.0 §2.2 for join-check validation)
            content_text: Text to embed
            model_version: Target embedding model version
        
        Returns:
            Celery task ID
        """
        job_data = {
            'job_id': job_id,
            'tenant_id': tenant_id,
            'chunk_id': chunk_id,
            'document_id': document_id,  # Per v7.0 §2.2: pass document_id for join-check validation
            'content_text': content_text,
            'model_version_target': model_version  # Task expects model_version_target
        }
        
        result = self.celery_app.send_task(
            'app.workers.embedding_worker.embedding_task',
            args=[job_data]
        )
        
        # DIAGNOSTIC: Print both IDs per v7.0 §2.4
        print(f"[DIAGNOSTIC] Enqueue: application job_id={job_id}, Celery task_id={result.id}")
        
        return result.id
    
    def enqueue_batch(
        self,
        jobs: list,
        enforce_tenant_isolation: bool = True
    ) -> list:
        """
        Enqueue multiple embedding jobs with optional batching.
        
        CRITICAL: If batching is used, all jobs in the batch MUST belong to the same tenant.
        This is enforced by the enforce_tenant_isolation parameter.
        
        Args:
            jobs: List of job data dictionaries
            enforce_tenant_isolation: Whether to enforce tenant isolation (default: True)
        
        Returns:
            List of Celery task IDs
        
        Raises:
            AssertionError: If batching across tenants is detected and isolation is enforced
        """
        if enforce_tenant_isolation and jobs:
            # Verify all jobs in batch belong to the same tenant
            tenant_ids = set(job.get('tenant_id') for job in jobs)
            
            if len(tenant_ids) > 1:
                raise AssertionError(
                    f"TENANT ISOLATION VIOLATION: Attempting to batch jobs from multiple tenants: {tenant_ids}. "
                    "Per §28.3, batching across tenants is prohibited even for throughput optimization."
                )
        
        task_ids = []
        for job in jobs:
            task_id = self.enqueue_job(
                job_id=job['job_id'],
                tenant_id=job['tenant_id'],
                chunk_id=job['chunk_id'],
                document_id=job.get('document_id'),  # Per v7.0 §2.2: pass document_id
                content_text=job['content_text'],
                model_version=job.get('model_version', job.get('model_version_target'))
            )
            task_ids.append(task_id)
        
        return task_ids
