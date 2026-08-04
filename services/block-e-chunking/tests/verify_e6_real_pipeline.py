"""
E6 Pipeline-Level Verification: Embedding Completeness (Real Pipeline)
Processes documents through the actual ingestion path:
CanonicalConsumer → real embedding job queue → real worker → chunk_records
Then samples chunk_records to verify embedding completeness.
"""

import asyncio
import sys
import os
import uuid
import time
import redis
import struct
from datetime import datetime
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celery import Celery
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text
from app.consumers.canonical_consumer import CanonicalConsumer
from app.workers.embedding_worker import EmbeddingJobQueue
from app.models.chunk_record import ChunkRecord, Base

# Configuration
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/block_e"
CELERY_BROKER_URL = "redis://localhost:6379/1"
CELERY_RESULT_BACKEND = "redis://localhost:6379/2"
REDIS_URL = "redis://localhost:6379/0"
PROVIDER_CALL_LOG_KEY = "embedding:provider_call_log"
NUM_DOCUMENTS = 50

def generate_canonical_documents(num_docs: int) -> List[dict]:
    """Generate synthetic canonical documents."""
    docs = []
    for i in range(num_docs):
        doc = {
            "tenant_id": f"tenant_{i % 3}",  # Rotate through 3 tenants
            "document_id": f"doc_{i}",
            "document_version": 1,
            "content_type": "prose",
            "title": f"Test Document {i}",
            "content": f"This is test content for document {i}. " * 10,  # ~250 chars
            "metadata": {"source": "e6_test"}
        }
        docs.append(doc)
    return docs


async def clear_chunk_records(session):
    """Clear existing chunk_records."""
    try:
        await session.execute(text("DELETE FROM chunk_records"))
    except:
        pass  # Table might not exist yet
    try:
        await session.execute(text("DELETE FROM embedding_jobs"))
    except:
        pass  # Table might not exist yet
    await session.commit()


def clear_provider_call_log(redis_client):
    """Clear the provider call log."""
    redis_client.delete(PROVIDER_CALL_LOG_KEY)


def wait_for_completion(redis_client: redis.Redis, expected_count: int, timeout: int = 60) -> bool:
    """Wait for completion by polling the provider call log."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        log_count = redis_client.llen(PROVIDER_CALL_LOG_KEY)
        if log_count >= expected_count:
            return True
        time.sleep(0.1)
    return False


async def verify_e6_real_pipeline():
    """Verify E6 using the real pipeline."""
    
    print("=" * 80)
    print("E6 Pipeline-Level Verification: Embedding Completeness (Real Pipeline)")
    print("=" * 80)
    
    # Setup PostgreSQL
    print("\n[1] Connecting to PostgreSQL database...")
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Create tables if they don't exist
    print("[1.1] Creating database tables if needed...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("   ✓ Tables created/verified")
    
    async with AsyncSessionLocal() as session:
        # Clear existing data
        print("[2] Clearing existing chunk_records...")
        await clear_chunk_records(session)
        print("   ✓ Cleared")
    
    # Setup Redis
    print("[3] Connecting to Redis...")
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    clear_provider_call_log(redis_client)
    print("   ✓ Connected and cleared provider call log")
    
    # Setup Celery
    print("[4] Setting up Celery...")
    celery_app = Celery(
        'embedding_worker',
        broker=CELERY_BROKER_URL,
        backend=CELERY_RESULT_BACKEND
    )
    queue = EmbeddingJobQueue(celery_app)
    print(f"   Broker: {CELERY_BROKER_URL}")
    print(f"   Backend: {CELERY_RESULT_BACKEND}")
    
    # Setup CanonicalConsumer
    print("[5] Setting up CanonicalConsumer...")
    consumer = CanonicalConsumer(DATABASE_URL, chunker_version="1.0.0", engine=engine, celery_app=celery_app)
    
    # Generate documents
    print(f"[6] Generating {NUM_DOCUMENTS} canonical documents...")
    docs = generate_canonical_documents(NUM_DOCUMENTS)
    print(f"   ✓ Generated {len(docs)} documents")
    
    # Process documents through CanonicalConsumer
    print(f"[7] Processing documents through CanonicalConsumer...")
    chunk_ids = []
    job_ids = []
    celery_task_ids = []
    
    async with AsyncSessionLocal() as session:
        for i, doc in enumerate(docs):
            event = {
                "tenant_id": doc["tenant_id"],
                "event_type": "canonical.v1",
                "payload": doc
            }
            
            try:
                result = await consumer.process_event(event)
                chunk_ids.append(result['chunk_id'])
                job_ids.append(result['job_id'])
                if result.get('celery_task_id'):
                    celery_task_ids.append(result['celery_task_id'])
                
                if (i + 1) % 10 == 0:
                    print(f"   Processed {i + 1}/{NUM_DOCUMENTS} documents")
            except Exception as e:
                print(f"   ✗ Error processing document {i}: {e}")
                return False
    
    print(f"   ✓ Processed {len(chunk_ids)} documents")
    print(f"   Created {len(chunk_ids)} chunk records")
    print(f"   Created {len(job_ids)} embedding jobs")
    print(f"   Captured {len(celery_task_ids)} Celery task IDs")
    
    # Wait for all embedding jobs to complete via provider call log
    print(f"\n[8] Waiting for {len(job_ids)} embedding jobs to complete...")
    print(f"   Polling provider call log: {PROVIDER_CALL_LOG_KEY}")
    
    if not wait_for_completion(redis_client, len(job_ids), timeout=120):
        print(f"   ✗ Timeout waiting for completion")
        print(f"   Provider call log count: {redis_client.llen(PROVIDER_CALL_LOG_KEY)}")
        return False
    
    print(f"   ✓ All {len(job_ids)} jobs completed")
    print(f"   Provider call log count: {redis_client.llen(PROVIDER_CALL_LOG_KEY)}")
    
    # NO EMBEDDING WRITE IN TEST SCRIPT - worker writes directly (Defect 12 fix)
    
    # Verify cross-tenant violations in provider call log
    print("\n[9] Verifying tenant isolation in provider call log...")
    log_entries = redis_client.lrange(PROVIDER_CALL_LOG_KEY, 0, -1)
    
    violations = []
    for entry in log_entries:
        if entry.count('tenant_id') != 1:
            violations.append(entry)
    
    if violations:
        print(f"   ✗ Found {len(violations)} cross-tenant violations")
        for v in violations[:3]:
            print(f"      {v}")
        return False
    
    print(f"   ✓ No cross-tenant violations in {len(log_entries)} provider call log entries")
    
    # Sample chunk_records for verification
    print("\n[10] Sampling chunk_records for embedding completeness...")
    
    async with AsyncSessionLocal() as session:
        # Get total count
        count_result = await session.execute(select(ChunkRecord).where(ChunkRecord.deleted_at.is_(None)))
        total_chunks = len(count_result.scalars().all())
        print(f"   Total chunks in database: {total_chunks}")
        
        if total_chunks < NUM_DOCUMENTS:
            print(f"   ✗ Expected at least {NUM_DOCUMENTS} chunks, got {total_chunks}")
            return False
        
        # Sample up to 100 chunks
        sample_size = min(100, total_chunks)
        sample_result = await session.execute(
            select(ChunkRecord).where(ChunkRecord.deleted_at.is_(None)).limit(sample_size)
        )
        sampled_chunks = sample_result.scalars().all()
        print(f"   Sampled {len(sampled_chunks)} chunks")
        
        # Check embedding completeness
        null_vectors = sum(1 for c in sampled_chunks if c.embedding_vector is None)
        null_model_versions = sum(1 for c in sampled_chunks if c.embedding_model_version is None)
        
        # Debug: print first chunk's embedding_vector status
        if sampled_chunks:
            first_chunk = sampled_chunks[0]
            print(f"\n[11.1] Debug: First chunk info:")
            print(f"   chunk_id: {first_chunk.chunk_id}")
            print(f"   embedding_vector: {first_chunk.embedding_vector}")
            print(f"   embedding_vector type: {type(first_chunk.embedding_vector)}")
            print(f"   embedding_model_version: {first_chunk.embedding_model_version}")
        
        print(f"\n[11] Checking embedding completeness...")
        print(f"   Total sampled: {len(sampled_chunks)}")
        print(f"   Chunks with non-null embedding_vector: {len(sampled_chunks) - null_vectors} ({(len(sampled_chunks) - null_vectors) / len(sampled_chunks) * 100:.1f}%)")
        print(f"   Chunks with null embedding_vector: {null_vectors}")
        print(f"   Chunks with non-null embedding_model_version: {len(sampled_chunks) - null_model_versions} ({(len(sampled_chunks) - null_model_versions) / len(sampled_chunks) * 100:.1f}%)")
        print(f"   Chunks with null embedding_model_version: {null_model_versions}")
        
        if null_vectors > 0:
            print(f"   ✗ Found {null_vectors} chunks with null embedding_vector")
            return False
        
        if null_model_versions > 0:
            print(f"   ✗ Found {null_model_versions} chunks with null embedding_model_version")
            return False
        
        # Check for stuck chunks (no embedding > 1 hour old)
        from datetime import timedelta
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        stuck_result = await session.execute(
            select(ChunkRecord).where(
                ChunkRecord.deleted_at.is_(None),
                ChunkRecord.embedding_vector.is_(None),
                ChunkRecord.created_at < one_hour_ago
            )
        )
        stuck_chunks = len(stuck_result.scalars().all())
        print(f"\n[12] Checking for permanently-queued chunks...")
        print(f"   Stuck chunks (no embedding > 1 hour old): {stuck_chunks}")
        
        if stuck_chunks > 0:
            print(f"   ✗ Found {stuck_chunks} stuck chunks")
            return False
    
    print("\n" + "=" * 80)
    print("E6 Pipeline-Level Verification Result")
    print("=" * 80)
    print(f"Total chunks in database: {total_chunks}")
    print(f"Sample size: {len(sampled_chunks)}")
    print(f"Vector completeness: 100.0%")
    print(f"Model version completeness: 100.0%")
    print(f"Stuck chunks: 0")
    print()
    print("✓ PASS: 100% of sampled rows have non-null embedding_vector")
    print("✓ PASS: 100% of sampled rows have non-null embedding_model_version")
    print("✓ PASS: 0 rows left in permanently-queued state")
    print()
    print("E6 Pipeline-Level Verification: VERIFIED")
    
    await engine.dispose()
    return True


if __name__ == "__main__":
    success = asyncio.run(verify_e6_real_pipeline())
    sys.exit(0 if success else 1)
