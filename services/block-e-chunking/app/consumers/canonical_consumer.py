"""
Component 1: Consumer for ingest.canonical.v1
Consumes canonical documents from Block C and creates chunk_records and embedding_jobs
"""

import json
import uuid
from typing import Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.chunkers.prose_chunker import ProseChunker
from app.chunkers.code_chunker import CodeChunker
from app.chunkers.chunk_id_generator import ChunkIDGenerator
from app.models.chunk_record import ChunkRecord, ChunkType
from app.models.embedding_job import EmbeddingJob, JobStatus
from app.workers.embedding_worker import EmbeddingJobQueue
from celery import Celery


class CanonicalConsumer:
    """
    Consumer for ingest.canonical.v1 events.
    
    Extracts tenant_id from the event envelope and never infers it from content.
    Creates chunk_records skeleton and embedding_jobs rows.
    """
    
    def __init__(self, database_url: str, chunker_version: str = "1.0.0", engine=None, celery_app=None):
        self.engine = engine if engine else create_async_engine(database_url)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.chunker_version = chunker_version
        self.chunk_id_generator = ChunkIDGenerator(chunker_version)
        self.celery_app = celery_app
        if celery_app:
            self.job_queue = EmbeddingJobQueue(celery_app)
    
    async def process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a canonical document event.
        
        Args:
            event: Kafka event with envelope containing tenant_id and payload with canonical document
        
        Returns:
            Processing result with created chunk and job IDs
        """
        # Extract tenant_id from event envelope (never from content)
        tenant_id = event.get("tenant_id")
        if not tenant_id:
            raise ValueError("tenant_id missing from event envelope")
        
        # Extract canonical document from payload
        payload = event.get("payload", {})
        document_id = payload.get("document_id")
        document_version = payload.get("document_version")
        content_type = payload.get("content_type")
        content = payload.get("content")
        
        if not document_id or not document_version or not content:
            raise ValueError("Missing required fields in canonical document payload")
        
        async with self.async_session() as session:
            # Create a skeleton chunk record (will be fully populated by chunker)
            # For now, create a placeholder to verify the consumer works
            content_hash = self.chunk_id_generator.compute_content_hash(content)
            chunk_id = self.chunk_id_generator.generate(
                tenant_id=tenant_id,
                document_id=document_id,
                document_version=document_version,
                chunk_type=ChunkType.FILE_SUMMARY.value,
                chunk_index=0,
                content_hash=content_hash
            )
            
            chunk_record = ChunkRecord(
                chunk_id=chunk_id,
                tenant_id=tenant_id,
                document_id=document_id,
                document_version=document_version,
                chunk_type=ChunkType.FILE_SUMMARY.value,
                chunk_index=0,
                chunk_text=content,
                token_count=len(content.split()),  # Placeholder
                start_byte=0,
                end_byte=len(content),
                embedding_vector=None,
                embedding_model_version=None,
                embedding_timestamp=None,
                chunker_version=self.chunker_version,
                content_hash=content_hash,
                chunk_content_checksum=content_hash,  # For idempotency
                source_run_id=f"canonical_{document_id}_{document_version}",
                deleted_at=None,
                created_at=datetime.utcnow(),  # Explicit for SQLite compatibility
                updated_at=datetime.utcnow()   # Explicit for SQLite compatibility
            )
            
            session.add(chunk_record)
            
            # Create embedding job
            job_id = uuid.uuid4().hex
            embedding_job = EmbeddingJob(
                job_id=job_id,
                celery_task_id=None,  # Will be set when task is enqueued
                tenant_id=tenant_id,
                chunk_id=chunk_id,
                document_id=document_id,  # Denormalized per v7.0 §2.2
                status=JobStatus.PENDING,
                model_version_target="v1",  # Will come from config
                attempt_count=0,
                last_error=None,
                created_at=datetime.utcnow(),  # Explicit for SQLite compatibility
                updated_at=datetime.utcnow()   # Explicit for SQLite compatibility
            )
            
            session.add(embedding_job)
            await session.commit()
            
            # Enqueue job to Celery if celery_app is provided
            if self.celery_app:
                task_id = self.job_queue.enqueue_job(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    chunk_id=chunk_id,
                    content_text=content,
                    model_version="v1"
                )
                # Store Celery task_id for later retrieval (Defect 11 fix)
                celery_task_id = task_id
            
            return {
                "chunk_id": chunk_id,
                "job_id": job_id,
                "celery_task_id": celery_task_id if self.celery_app else None,
                "tenant_id": tenant_id,
                "document_id": document_id,
                "document_version": document_version
            }
    
    async def close(self):
        """Close database connections."""
        await self.engine.dispose()
