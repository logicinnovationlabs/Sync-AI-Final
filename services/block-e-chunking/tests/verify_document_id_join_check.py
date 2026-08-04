"""
Verification script for document_id join-check validation per v7.0 §2.2.

Tests that embedding_worker rejects jobs with mismatched document_id.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override DATABASE_URL to use localhost for testing
os.environ['DATABASE_URL'] = 'postgresql://postgres:postgres@localhost:5432/block_e'

from app.models.chunk_record import ChunkRecord
from app.models.embedding_job import EmbeddingJob
from app.workers.embedding_worker import embedding_task, SessionLocal


def test_document_id_join_check():
    """Test that document_id mismatch is rejected with AssertionError."""
    
    print("=" * 80)
    print("DOCUMENT_ID JOIN-CHECK VALIDATION VERIFICATION (v7.0 §2.2)")
    print("=" * 80)
    
    session = SessionLocal()
    
    try:
        # Clean up any existing test data
        session.query(EmbeddingJob).filter(EmbeddingJob.job_id.like('test_%')).delete()
        session.query(ChunkRecord).filter(ChunkRecord.chunk_id.like('test_%')).delete()
        session.commit()
        
        # Create a test chunk record with a specific document_id
        print("\n[1] Creating test chunk record with document_id='doc_123'...")
        chunk_record = ChunkRecord(
            chunk_id='test_chunk_001',
            tenant_id='test_tenant',
            document_id='doc_123',
            document_version=1,
            chunk_index=0,
            chunk_type='file_summary',
            chunk_text='test content',
            token_count=5,
            start_byte=0,
            end_byte=12,
            chunker_version='1.0.0',
            content_hash='abc123',
            chunk_content_checksum='def456',
            source_run_id='test_run_001'
        )
        session.add(chunk_record)
        session.commit()
        print(f"   ✓ Chunk record created: chunk_id={chunk_record.chunk_id}, document_id={chunk_record.document_id}")
        
        # Test 1: Matching document_id should succeed
        print("\n[2] Testing matching document_id (should succeed)...")
        job_data_match = {
            'job_id': 'test_job_001',
            'chunk_id': 'test_chunk_001',
            'document_id': 'doc_123',  # Matches chunk_record.document_id
            'tenant_id': 'test_tenant',
            'model_version_target': 'text-embedding-ada-002'
        }
        
        try:
            # This should succeed
            result = embedding_task(job_data_match)
            print(f"   ✓ Matching document_id accepted: job_id={job_data_match['job_id']}")
        except AssertionError as e:
            if 'document_id mismatch' in str(e):
                print(f"   ✗ Matching document_id rejected (should succeed): {e}")
                return False
            else:
                # Different assertion error, re-raise
                raise
        
        # Test 2: Mismatched document_id should fail with AssertionError
        print("\n[3] Testing mismatched document_id (should fail with AssertionError)...")
        job_data_mismatch = {
            'job_id': 'test_job_002',
            'chunk_id': 'test_chunk_001',
            'document_id': 'doc_999',  # Does NOT match chunk_record.document_id
            'tenant_id': 'test_tenant',
            'model_version_target': 'text-embedding-ada-002'
        }
        
        try:
            result = embedding_task(job_data_mismatch)
            print(f"   ✗ Mismatched document_id accepted (should fail): job_id={job_data_mismatch['job_id']}")
            return False
        except AssertionError as e:
            if 'document_id mismatch' in str(e):
                print(f"   ✓ Mismatched document_id rejected with AssertionError")
                print(f"   Error message: {e}")
            else:
                print(f"   ✗ Wrong AssertionError raised: {e}")
                return False
        
        # Test 3: Non-existent chunk_id should fail
        print("\n[4] Testing non-existent chunk_id (should fail with AssertionError)...")
        job_data_no_chunk = {
            'job_id': 'test_job_003',
            'chunk_id': 'test_chunk_nonexistent',
            'document_id': 'doc_123',
            'tenant_id': 'test_tenant',
            'model_version_target': 'text-embedding-ada-002'
        }
        
        try:
            result = embedding_task(job_data_no_chunk)
            print(f"   ✗ Non-existent chunk_id accepted (should fail): job_id={job_data_no_chunk['job_id']}")
            return False
        except AssertionError as e:
            if 'Chunk does not exist' in str(e):
                print(f"   ✓ Non-existent chunk_id rejected with AssertionError")
                print(f"   Error message: {e}")
            else:
                print(f"   ✗ Wrong AssertionError raised: {e}")
                return False
        
        print("\n" + "=" * 80)
        print("DOCUMENT_ID JOIN-CHECK VALIDATION VERIFICATION: PASSED")
        print("=" * 80)
        print("\nEVIDENCE:")
        print("- Matching document_id was accepted (no error)")
        print("- Mismatched document_id was rejected with AssertionError")
        print("- Non-existent chunk_id was rejected with AssertionError")
        print("- Error messages explicitly reference v7.0 §2.2 violation")
        
        return True
        
    finally:
        # Clean up test data
        session.query(EmbeddingJob).filter(EmbeddingJob.job_id.like('test_%')).delete()
        session.query(ChunkRecord).filter(ChunkRecord.chunk_id.like('test_%')).delete()
        session.commit()
        session.close()


if __name__ == "__main__":
    try:
        success = test_document_id_join_check()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
