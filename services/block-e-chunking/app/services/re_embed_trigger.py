"""
Component 6: Re-embed trigger for model version bumps.
"""

import uuid
from datetime import datetime

from typing import List, Dict, Any
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk_record import ChunkRecord
from app.models.embedding_job import EmbeddingJob


class ReEmbedTrigger:
    """
    Triggers re-embedding when embedding_model_version changes.
    
    Per §10.6: When embedding_model_version is bumped, all chunks for a tenant
    should be re-embedded with the new model version. This is tenant-scoped enqueuing.
    """
    
    def __init__(self, db_session: AsyncSession, celery_app=None):
        self.db_session = db_session
        self.celery_app = celery_app
    
    async def get_current_model_version(self, tenant_id: str) -> str:
        """
        Get the current embedding model version for a tenant.
        
        Args:
            tenant_id: Tenant identifier
        
        Returns:
            Current embedding_model_version for the tenant
        """
        # Get the most recent embedding_model_version from chunk records
        result = await self.db_session.execute(
            select(ChunkRecord.embedding_model_version)
            .where(ChunkRecord.tenant_id == tenant_id)
            .where(ChunkRecord.embedding_model_version.isnot(None))
            .order_by(ChunkRecord.created_at.desc())
            .limit(1)
        )
        
        row = result.scalar_one_or_none()
        return row if row else "v1"  # Default to v1 if no chunks exist
    
    async def detect_version_change(
        self,
        tenant_id: str,
        new_model_version: str
    ) -> bool:
        """
        Detect if embedding_model_version has changed for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            new_model_version: New model version to check against
        
        Returns:
            True if version changed, False otherwise
        """
        current_version = await self.get_current_model_version(tenant_id)
        return current_version != new_model_version
    
    async def enqueue_re_embed_jobs(
        self,
        tenant_id: str,
        new_model_version: str
    ) -> List[str]:
        """
        Enqueue re-embedding jobs for all chunks of a tenant.
        
        This is tenant-scoped enqueuing per §10.6 - only chunks from the
        specified tenant are queued for re-embedding.
        
        Args:
            tenant_id: Tenant identifier
            new_model_version: New embedding model version
        
        Returns:
            List of job IDs for enqueued re-embedding jobs
        """
        # Get all chunks for the tenant
        result = await self.db_session.execute(
            select(ChunkRecord).where(ChunkRecord.tenant_id == tenant_id)
        )
        chunks = result.scalars().all()
        
        job_ids = []
        
        if self.celery_app:
            # Use Celery job queue if available
            from app.workers.embedding_worker import EmbeddingJobQueue
            job_queue = EmbeddingJobQueue(self.celery_app)
            
            for chunk in chunks:
                job_id = f"reembed_{tenant_id}_{chunk.chunk_id}_{new_model_version}"
                
                # Create embedding job record
                job = EmbeddingJob(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    status="pending",
                    model_version_target=new_model_version,
                    attempt_count=0,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                self.db_session.add(job)
                
                # Enqueue to Celery
                celery_task_id = job_queue.enqueue_job(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    content_text=chunk.chunk_text,
                    model_version=new_model_version
                )
                
                job_ids.append(job_id)
            
            await self.db_session.commit()
            
            print(f"[RE-EMBED] Enqueued {len(job_ids)} re-embedding jobs to Celery for tenant {tenant_id}")
            print(f"[RE-EMBED] New model version: {new_model_version}")
        else:
            # Fallback: only create job records (no Celery enqueuing)
            for chunk in chunks:
                job = EmbeddingJob(
                    job_id=f"reembed_{tenant_id}_{chunk.chunk_id}_{new_model_version}",
                    tenant_id=tenant_id,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    status="pending",
                    model_version_target=new_model_version,
                    attempt_count=0,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                self.db_session.add(job)
                job_ids.append(job.job_id)
            
            await self.db_session.commit()
            
            print(f"[RE-EMBED] Created {len(job_ids)} re-embedding job records for tenant {tenant_id} (no Celery enqueuing)")
            print(f"[RE-EMBED] New model version: {new_model_version}")
        
        return job_ids
    
    async def trigger_re_embed(
        self,
        tenant_id: str,
        new_model_version: str
    ) -> Dict[str, Any]:
        """
        Trigger re-embedding for a tenant if model version changed.
        
        Args:
            tenant_id: Tenant identifier
            new_model_version: New embedding model version
        
        Returns:
            Dictionary with trigger results
        """
        # Check if version changed
        version_changed = await self.detect_version_change(tenant_id, new_model_version)
        
        if not version_changed:
            return {
                "tenant_id": tenant_id,
                "triggered": False,
                "reason": "Model version unchanged",
                "current_version": await self.get_current_model_version(tenant_id),
                "new_version": new_model_version
            }
        
        # Enqueue re-embedding jobs
        job_ids = await self.enqueue_re_embed_jobs(tenant_id, new_model_version)
        
        return {
            "tenant_id": tenant_id,
            "triggered": True,
            "reason": "Model version changed",
            "current_version": await self.get_current_model_version(tenant_id),
            "new_version": new_model_version,
            "jobs_enqueued": len(job_ids),
            "job_ids": job_ids
        }
    
    async def update_chunk_model_version(
        self,
        tenant_id: str,
        new_model_version: str
    ) -> int:
        """
        Update embedding_model_version for all chunks of a tenant.
        
        This is called after re-embedding completes to mark chunks as
        having been embedded with the new model version.
        
        Args:
            tenant_id: Tenant identifier
            new_model_version: New embedding model version
        
        Returns:
            Number of chunks updated
        """
        result = await self.db_session.execute(
            update(ChunkRecord)
            .where(ChunkRecord.tenant_id == tenant_id)
            .values(embedding_model_version=new_model_version)
        )
        
        await self.db_session.commit()
        
        count = result.rowcount
        print(f"[RE-EMBED] Updated embedding_model_version to {new_model_version} for {count} chunks")
        
        return count
