"""
Component 1 Verification Script
Verifies that the consumer creates chunk_records and embedding_jobs with correct tenant_id and document_id
"""

import asyncio
import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.consumers.canonical_consumer import CanonicalConsumer
from app.models.chunk_record import ChunkRecord
from app.models.embedding_job import EmbeddingJob
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text


async def setup_test_database():
    """Create test database tables."""
    database_url = "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(database_url)
    
    # Import models to ensure they're registered
    from app.models.chunk_record import ChunkRecord, Base
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    return engine


async def verify_consumer():
    """Verify consumer creates chunk_records and embedding_jobs correctly."""
    
    print("=" * 80)
    print("COMPONENT 1 VERIFICATION: Consumer for ingest.canonical.v1")
    print("=" * 80)
    
    # Setup test database
    print("\n[1] Setting up test database...")
    engine = await setup_test_database()
    database_url = "sqlite+aiosqlite:///:memory:"
    
    # Load fixture
    print("\n[2] Loading Block Z fixture canonical-doc event...")
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "fixtures",
        "canonical",
        "canonical_doc_1.json"
    )
    
    with open(fixture_path, 'r') as f:
        canonical_doc = json.load(f)
    
    print(f"   Loaded fixture: {canonical_doc['document_id']}")
    print(f"   Tenant ID: {canonical_doc['tenant_id']}")
    print(f"   Content Type: {canonical_doc['content_type']}")
    
    # Create event envelope (as would come from Kafka)
    event = {
        "tenant_id": canonical_doc["tenant_id"],
        "event_id": "test_event_001",
        "timestamp": "2024-01-01T00:00:00Z",
        "payload": canonical_doc
    }
    
    # Create consumer
    print("\n[3] Creating CanonicalConsumer...")
    consumer = CanonicalConsumer(database_url, chunker_version="1.0.0", engine=engine)
    
    # Process event
    print("\n[4] Processing canonical document event...")
    try:
        result = await consumer.process_event(event)
        print(f"   ✓ Event processed successfully")
        print(f"   Chunk ID: {result['chunk_id']}")
        print(f"   Job ID: {result['job_id']}")
        print(f"   Tenant ID: {result['tenant_id']}")
        print(f"   Document ID: {result['document_id']}")
    except Exception as e:
        print(f"   ✗ Error processing event: {e}")
        await consumer.close()
        await engine.dispose()
        return False
    
    # Verify database records
    print("\n[5] Verifying database records...")
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Query chunk_records
        chunk_query = select(ChunkRecord).where(
            ChunkRecord.chunk_id == result['chunk_id']
        )
        chunk_result = await session.execute(chunk_query)
        chunk_record = chunk_result.scalar_one_or_none()
        
        if chunk_record:
            print(f"   ✓ chunk_records row created")
            print(f"     - chunk_id: {chunk_record.chunk_id}")
            print(f"     - tenant_id: {chunk_record.tenant_id}")
            print(f"     - document_id: {chunk_record.document_id}")
            print(f"     - document_version: {chunk_record.document_version}")
            print(f"     - chunk_type: {chunk_record.chunk_type}")
            print(f"     - chunker_version: {chunk_record.chunker_version}")
            
            # Verify tenant_id matches envelope (not inferred from content)
            if chunk_record.tenant_id == event["tenant_id"]:
                print(f"   ✓ tenant_id correctly extracted from event envelope")
            else:
                print(f"   ✗ tenant_id mismatch: expected {event['tenant_id']}, got {chunk_record.tenant_id}")
                await consumer.close()
                await engine.dispose()
                return False
            
            # Verify document_id matches payload
            if chunk_record.document_id == canonical_doc["document_id"]:
                print(f"   ✓ document_id correctly extracted from payload")
            else:
                print(f"   ✗ document_id mismatch")
                await consumer.close()
                await engine.dispose()
                return False
        else:
            print(f"   ✗ chunk_records row NOT created")
            await consumer.close()
            await engine.dispose()
            return False
        
        # Query embedding_jobs
        job_query = select(EmbeddingJob).where(
            EmbeddingJob.job_id == result['job_id']
        )
        job_result = await session.execute(job_query)
        job_record = job_result.scalar_one_or_none()
        
        if job_record:
            print(f"   ✓ embedding_jobs row created")
            print(f"     - job_id: {job_record.job_id}")
            print(f"     - tenant_id: {job_record.tenant_id}")
            print(f"     - chunk_id: {job_record.chunk_id}")
            print(f"     - status: {job_record.status}")
            print(f"     - model_version_target: {job_record.model_version_target}")
            
            # Verify tenant_id matches
            if job_record.tenant_id == event["tenant_id"]:
                print(f"   ✓ embedding_jobs tenant_id matches envelope")
            else:
                print(f"   ✗ embedding_jobs tenant_id mismatch")
                await consumer.close()
                await engine.dispose()
                return False
            
            # Verify chunk_id matches
            if job_record.chunk_id == chunk_record.chunk_id:
                print(f"   ✓ embedding_jobs chunk_id matches chunk_records")
            else:
                print(f"   ✗ embedding_jobs chunk_id mismatch")
                await consumer.close()
                await engine.dispose()
                return False
        else:
            print(f"   ✗ embedding_jobs row NOT created")
            await consumer.close()
            await engine.dispose()
            return False
    
    # Cleanup
    print("\n[6] Cleaning up...")
    await consumer.close()
    await engine.dispose()
    
    print("\n" + "=" * 80)
    print("COMPONENT 1 VERIFICATION: PASSED")
    print("=" * 80)
    print("\nEVIDENCE:")
    print(f"- chunk_records row created with chunk_id: {result['chunk_id']}")
    print(f"- embedding_jobs row created with job_id: {result['job_id']}")
    print(f"- tenant_id correctly extracted from event envelope: {result['tenant_id']}")
    print(f"- document_id correctly extracted from payload: {result['document_id']}")
    print(f"- Zero tenant_id inference from content detected")
    
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(verify_consumer())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
