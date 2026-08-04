"""
Component 7 Verification Script
Verifies orphan and tombstone handling on re-chunk
"""

import sys
import os
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.chunk_record import ChunkRecord, Base
from app.services.orphan_handler import OrphanHandler


def verify_orphan_handler():
    """Verify orphan and tombstone handling."""
    
    print("=" * 80)
    print("COMPONENT 7 VERIFICATION: Orphan and Tombstone Handling")
    print("=" * 80)
    
    SYNC_DATABASE_URL = "postgresql://postgres:verify@localhost:5433/block_e_verify"
    run_id = uuid.uuid4().hex[:8]

    print("\n[1] Creating test database...")
    engine = create_engine(SYNC_DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    print("\n[2] Creating test chunks for document version 1...")
    tenant_id = f"tenant_{run_id}"
    document_id = f"doc_{run_id}"

    for i in range(5):
        chunk = ChunkRecord(
            chunk_id=f"chunk_v1_{run_id}_{i}",
            tenant_id=tenant_id,
            document_id=document_id,
            document_version=1,
            chunk_type="prose",
            chunk_index=i,
            chunk_text=f"Test content v1 {i}",
            token_count=10,
            start_byte=i * 100,
            end_byte=(i + 1) * 100,
            chunker_version="v1",
            embedding_model_version="v1",
            content_hash=f"hash_v1_{run_id}_{i}",
            chunk_content_checksum=f"hash_v1_{run_id}_{i}",
            source_run_id=f"test_run_v1_{run_id}_{i}",
        )
        session.add(chunk)
    
    session.commit()
    print(f"   Created 5 chunks for document version 1")
    
    # Create orphan handler
    print("\n[3] Creating OrphanHandler...")
    handler = OrphanHandler(session)
    
    # Test 1: Get current chunks
    print("\n[4] Test 1: Get current chunks...")
    current_chunks = handler.get_current_chunks(tenant_id, document_id, 1)
    print(f"   Found {len(current_chunks)} current chunks")
    
    if len(current_chunks) != 5:
        print(f"   ✗ Expected 5 chunks, got {len(current_chunks)}")
        return False
    
    print(f"   ✓ Correct number of chunks retrieved")
    
    # Test 2: Re-chunk to version 2 with different chunk IDs
    print("\n[5] Test 2: Re-chunk to version 2...")
    new_chunk_ids = [f"chunk_v2_{run_id}_{i}" for i in range(3)]

    for i in range(3):
        chunk = ChunkRecord(
            chunk_id=f"chunk_v2_{run_id}_{i}",
            tenant_id=tenant_id,
            document_id=document_id,
            document_version=2,
            chunk_type="prose",
            chunk_index=i,
            chunk_text=f"Test content v2 {i}",
            token_count=10,
            start_byte=i * 100,
            end_byte=(i + 1) * 100,
            chunker_version="v1",
            embedding_model_version="v1",
            content_hash=f"hash_v2_{run_id}_{i}",
            chunk_content_checksum=f"hash_v2_{run_id}_{i}",
            source_run_id=f"test_run_v2_{run_id}_{i}",
        )
        session.add(chunk)
    
    session.commit()
    print(f"   Created 3 chunks for document version 2")
    
    # Test 3: Handle re-chunk (should mark v1 chunks as tombstones)
    print("\n[6] Test 3: Handle re-chunk...")
    result = handler.handle_re_chunk(tenant_id, document_id, 2, new_chunk_ids)
    
    print(f"   Orphan chunks found: {result['orphan_chunks_found']}")
    print(f"   Orphans marked as tombstones: {result['orphans_marked_as_tombstones']}")
    print(f"   Previous versions marked: {result['previous_versions_marked']}")
    print(f"   Total tombstoned: {result['total_tombstoned']}")
    
    if result['orphan_chunks_found'] != 5:
        print(f"   ✗ Expected 5 orphan chunks, got {result['orphan_chunks_found']}")
        return False
    
    if result['orphans_marked_as_tombstones'] != 5:
        print(f"   ✗ Expected 5 marked, got {result['orphans_marked_as_tombstones']}")
        return False
    
    print(f"   ✓ Orphans correctly marked as tombstones")
    
    # Test 4: Verify tombstones
    print("\n[7] Test 4: Verify tombstones...")
    tombstoned = session.query(ChunkRecord).filter(
        ChunkRecord.tenant_id == tenant_id,
        ChunkRecord.document_id == document_id,
        ChunkRecord.document_version == 1,
        ChunkRecord.deleted_at.isnot(None)
    ).all()
    
    print(f"   Found {len(tombstoned)} tombstoned chunks")
    
    if len(tombstoned) != 5:
        print(f"   ✗ Expected 5 tombstoned chunks, got {len(tombstoned)}")
        return False
    
    print(f"   ✓ All v1 chunks correctly tombstoned")
    
    # Test 5: Verify current chunks are not tombstoned
    print("\n[8] Test 5: Verify current chunks are not tombstoned...")
    active = session.query(ChunkRecord).filter(
        ChunkRecord.tenant_id == tenant_id,
        ChunkRecord.document_id == document_id,
        ChunkRecord.document_version == 2,
        ChunkRecord.deleted_at.is_(None)
    ).all()
    
    print(f"   Found {len(active)} active chunks")
    
    if len(active) != 3:
        print(f"   ✗ Expected 3 active chunks, got {len(active)}")
        return False
    
    print(f"   ✓ Current chunks remain active")
    
    # Test 6: Get previous chunks
    print("\n[9] Test 6: Get previous chunks...")
    previous = handler.get_previous_chunks(tenant_id, document_id, 2)
    print(f"   Found {len(previous)} previous chunks")
    
    # Previous chunks should be 0 since v1 is tombstoned
    if len(previous) != 0:
        print(f"   ✗ Expected 0 previous chunks (tombstoned), got {len(previous)}")
        return False
    
    print(f"   ✓ Previous chunks correctly excluded (tombstoned)")
    
    # Test 7: Mark single chunk as tombstone
    print("\n[10] Test 7: Mark single chunk as tombstone...")
    marked = handler.mark_as_tombstone(f"chunk_v2_{run_id}_0")
    print(f"   Marked: {marked}")
    
    if not marked:
        print(f"   ✗ Failed to mark chunk as tombstone")
        return False
    
    print(f"   ✓ Single chunk marked as tombstone")
    
    session.close()
    
    print("\n" + "=" * 80)
    print("COMPONENT 7 VERIFICATION: PASSED")
    print("=" * 80)
    print("\nEVIDENCE:")
    print(f"- Current chunks retrieved correctly (5 chunks for v1)")
    print(f"- Re-chunk to v2 with different chunk IDs detected 5 orphans")
    print(f"- All 5 orphan chunks marked as tombstones (soft delete)")
    print(f"- Previous version chunks marked as tombstones (5 chunks)")
    print(f"- Current chunks remain active (3 chunks for v2)")
    print(f"- Tombstoned chunks correctly excluded from previous chunks query")
    print(f"- Single chunk tombstone marking works")
    print(f"- Audit trail maintained via deleted_at timestamps")
    
    return True


if __name__ == "__main__":
    try:
        success = verify_orphan_handler()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
