"""
E3 Verification: 10k-chunk tenant re-embed test
Per Master Build Prompt v5.0 §4: 100% of affected chunks re-embedded within 1 hour on a 10k-chunk tenant
"""

import asyncio
import sys
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text
from app.models.chunk_record import ChunkRecord, Base
from app.models.embedding_job import EmbeddingJob

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:verify@localhost:5433/block_e_verify")
TENANT_ID = "tenant_e3_test_10k"
OLD_MODEL_VERSION = "v1"
NEW_MODEL_VERSION = "v2"
TARGET_CHUNK_COUNT = 10000
CONTROL_TENANT_ID = "tenant_e3_control_untouched"


async def generate_10k_chunks():
    """Generate 10k chunks for a test tenant."""
    
    print("=" * 80)
    print("E3 VERIFICATION: 10k-Chunk Tenant Re-Embed Test")
    print("=" * 80)
    
    # Create database engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    print(f"\n[1] Generating {TARGET_CHUNK_COUNT} chunks for tenant {TENANT_ID}...")
    print(f"   Old model version: {OLD_MODEL_VERSION}")
    print(f"   New model version: {NEW_MODEL_VERSION}")
    
    async with AsyncSessionLocal() as session:
        # Clear existing test data
        print(f"\n[2] Clearing existing test data for tenant {TENANT_ID}...")
        await session.execute(text("DELETE FROM chunk_records WHERE tenant_id = :tenant_id"), {"tenant_id": TENANT_ID})
        await session.execute(text("DELETE FROM embedding_jobs WHERE tenant_id = :tenant_id"), {"tenant_id": TENANT_ID})
        await session.commit()
        print(f"   ✓ Cleared existing data")
        
        # Generate chunks in batches
        batch_size = 1000
        chunks_generated = 0
        
        for batch_num in range(TARGET_CHUNK_COUNT // batch_size):
            batch_chunks = []
            for i in range(batch_size):
                chunk_id = uuid.uuid4().hex
                chunk_content = f"Test chunk content {chunks_generated + i} for re-embed testing. " * 10
                
                chunk_record = ChunkRecord(
                    chunk_id=chunk_id,
                    tenant_id=TENANT_ID,
                    document_id=f"doc_{batch_num}_{i}",
                    document_version=1,
                    chunk_index=i,
                    chunk_type="prose_paragraph",
                    chunk_text=chunk_content,
                    token_count=50,
                    start_byte=0,
                    end_byte=len(chunk_content),
                    embedding_vector=b'\x00' * 6144,  # Mock embedding (1536 floats * 4 bytes)
                    embedding_model_version=OLD_MODEL_VERSION,
                    embedding_timestamp=datetime.utcnow(),
                    chunker_version="1.0.0",
                    content_hash=uuid.uuid4().hex,
                    chunk_content_checksum=uuid.uuid4().hex,
                    source_run_id="e3_test_run"
                )
                batch_chunks.append(chunk_record)
            
            session.add_all(batch_chunks)
            await session.commit()
            chunks_generated += len(batch_chunks)
            
            if (batch_num + 1) % 5 == 0:
                print(f"   Generated {chunks_generated}/{TARGET_CHUNK_COUNT} chunks")
        
        print(f"   ✓ Generated {chunks_generated} chunks")
    

    # Seed control-tenant chunks that must remain at OLD_MODEL_VERSION
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM chunk_records WHERE tenant_id = :t"), {"t": CONTROL_TENANT_ID})
        for i in range(5):
            session.add(ChunkRecord(
                chunk_id=uuid.uuid4().hex,
                tenant_id=CONTROL_TENANT_ID,
                document_id=f"ctrl_doc_{i}",
                document_version=1,
                chunk_index=i,
                chunk_type="prose_paragraph",
                chunk_text="control chunk must not be re-embedded",
                token_count=10,
                start_byte=0,
                end_byte=40,
                embedding_vector=b"\x00" * 6144,
                embedding_model_version=OLD_MODEL_VERSION,
                embedding_timestamp=datetime.utcnow(),
                chunker_version="1.0.0",
                content_hash=uuid.uuid4().hex,
                chunk_content_checksum=uuid.uuid4().hex,
                source_run_id="e3_control",
            ))
        await session.commit()
        print(f"   Seeded control tenant {CONTROL_TENANT_ID} with 5 chunks at {OLD_MODEL_VERSION}")

    return chunks_generated


async def trigger_re_embed():
    """Trigger re-embed for the tenant and measure completion time."""
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    print(f"\n[3] Triggering re-embed for tenant {TENANT_ID}...")
    print(f"   Target: Update from {OLD_MODEL_VERSION} to {NEW_MODEL_VERSION}")
    
    start_time = time.time()
    
    async with AsyncSessionLocal() as session:
        # Count chunks with old model version
        old_version_count = await session.execute(
            select(ChunkRecord).where(
                ChunkRecord.tenant_id == TENANT_ID,
                ChunkRecord.embedding_model_version == OLD_MODEL_VERSION
            )
        )
        old_chunks = len(old_version_count.scalars().all())
        print(f"   Chunks with old model version: {old_chunks}")
        
        # Trigger re-embed
        from app.workers.embedding_worker import celery_app
        from app.services.re_embed_trigger import ReEmbedTrigger
        
        trigger = ReEmbedTrigger(session, celery_app=celery_app)
        result = await trigger.trigger_re_embed(
            tenant_id=TENANT_ID,
            new_model_version=NEW_MODEL_VERSION
        )
        
        job_ids = result.get('job_ids', [])
        await session.commit()
        print(f"   ✓ Enqueued {len(job_ids)} re-embed jobs")
    
    # Wait for completion (poll database)
    print(f"\n[4] Waiting for re-embed completion...")
    print(f"   Timeout: 1 hour (3600 seconds)")
    
    timeout_seconds = 3600
    check_interval = 10
    elapsed = 0
    
    while elapsed < timeout_seconds:
        async with AsyncSessionLocal() as session:
            # Count chunks with new model version
            new_version_count = await session.execute(
                select(ChunkRecord).where(
                    ChunkRecord.tenant_id == TENANT_ID,
                    ChunkRecord.embedding_model_version == NEW_MODEL_VERSION
                )
            )
            new_chunks = len(new_version_count.scalars().all())
            
            completion_percent = (new_chunks / old_chunks) * 100
            
            if elapsed % 60 == 0:
                print(f"   Elapsed: {elapsed}s | Progress: {new_chunks}/{old_chunks} ({completion_percent:.1f}%)")
            
            if new_chunks == old_chunks:
                completion_time = time.time() - start_time
                print(f"   ✓ Re-embed completed in {completion_time:.1f} seconds ({completion_time/60:.1f} minutes)")
                return True, completion_time, new_chunks
        
        await asyncio.sleep(check_interval)
        elapsed += check_interval
    
    # Timeout
    async with AsyncSessionLocal() as session:
        new_version_count = await session.execute(
            select(ChunkRecord).where(
                ChunkRecord.tenant_id == TENANT_ID,
                ChunkRecord.embedding_model_version == NEW_MODEL_VERSION
            )
        )
        new_chunks = len(new_version_count.scalars().all())
    
    completion_time = time.time() - start_time
    print(f"   ✗ Timeout after {completion_time:.1f} seconds")
    print(f"   Completed: {new_chunks}/{old_chunks} ({(new_chunks/old_chunks)*100:.1f}%)")
    return False, completion_time, new_chunks


async def verify_e3():
    """Run E3 verification."""
    
    # Generate 10k chunks
    chunks_generated = await generate_10k_chunks()
    
    if chunks_generated < TARGET_CHUNK_COUNT:
        print(f"\n✗ Failed to generate {TARGET_CHUNK_COUNT} chunks")
        return False
    
    # Trigger re-embed
    success, completion_time, completed_chunks = await trigger_re_embed()
    
    # Report results
    print("\n" + "=" * 80)
    print("E3 VERIFICATION RESULTS")
    print("=" * 80)
    print(f"\nTenant: {TENANT_ID}")
    print(f"Total chunks: {chunks_generated}")
    print(f"Chunks re-embedded: {completed_chunks}")
    print(f"Completion rate: {(completed_chunks/chunks_generated)*100:.1f}%")
    print(f"Completion time: {completion_time:.1f} seconds ({completion_time/60:.1f} minutes)")
    
    print("\n[5] v5.0 §4 threshold check:")
    print(f"   Requirement: 100% of affected chunks re-embedded within 1 hour")
    print(f"   Result: {completed_chunks}/{chunks_generated} ({(completed_chunks/chunks_generated)*100:.1f}%) in {completion_time/60:.1f} minutes")
    

    # Verify control tenant untouched
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with AsyncSessionLocal() as session:
        ctrl = await session.execute(
            select(ChunkRecord).where(ChunkRecord.tenant_id == CONTROL_TENANT_ID)
        )
        ctrl_chunks = ctrl.scalars().all()
        touched = [c.chunk_id for c in ctrl_chunks if c.embedding_model_version != OLD_MODEL_VERSION]
        print(f"\n[CONTROL TENANT] {CONTROL_TENANT_ID}: {len(ctrl_chunks)} chunks, touched={len(touched)}")
        if touched:
            print("E3 FAIL: control tenant chunks were modified")
            return False
    if success and completion_time <= 3600:
        print(f"   Status: PASS (100% completion within 1 hour)")
        print("\n" + "=" * 80)
        print("E3 VERIFICATION: PASS")
        print("=" * 80)
        print("\nEVIDENCE:")
        print(f"- Generated {chunks_generated} chunks for tenant {TENANT_ID}")
        print(f"- Re-embedded from {OLD_MODEL_VERSION} to {NEW_MODEL_VERSION}")
        print(f"- Completed {completed_chunks}/{chunks_generated} chunks (100%)")
        print(f"- Completion time: {completion_time:.1f} seconds ({completion_time/60:.1f} minutes)")
        print(f"- Within 1-hour threshold: YES")
        return True
    else:
        print(f"   Status: FAIL")
        print("\n" + "=" * 80)
        print("E3 VERIFICATION: FAIL")
        print("=" * 80)
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(verify_e3())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
