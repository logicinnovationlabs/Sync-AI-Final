"""
Component 2 Verification Script
Verifies deterministic chunk ID scheme - hash the same chunk 5 times, confirm identical output
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chunkers.chunk_id_generator import ChunkIDGenerator


def verify_chunk_id_determinism():
    """Verify that chunk IDs are deterministic - same inputs always produce same hash."""
    
    print("=" * 80)
    print("COMPONENT 2 VERIFICATION: Deterministic Chunk ID Scheme")
    print("=" * 80)
    
    # Create chunk ID generator
    print("\n[1] Creating ChunkIDGenerator with chunker_version='1.0.0'...")
    generator = ChunkIDGenerator(chunker_version="1.0.0")
    
    # Define test inputs
    print("\n[2] Defining test chunk parameters...")
    tenant_id = "tenant_001"
    document_id = "doc_001"
    document_version = 1
    chunk_type = "file_summary"
    chunk_index = 0
    content_text = "Machine learning is a subset of artificial intelligence."
    
    print(f"   tenant_id: {tenant_id}")
    print(f"   document_id: {document_id}")
    print(f"   document_version: {document_version}")
    print(f"   chunk_type: {chunk_type}")
    print(f"   chunk_index: {chunk_index}")
    print(f"   content_text: {content_text}")
    
    # Compute content hash
    print("\n[3] Computing content hash...")
    content_hash = generator.compute_content_hash(content_text)
    print(f"   content_hash: {content_hash}")
    
    # Generate chunk ID 5 times
    print("\n[4] Generating chunk_id 5 times with identical inputs...")
    chunk_ids = []
    for i in range(5):
        chunk_id = generator.generate(
            tenant_id=tenant_id,
            document_id=document_id,
            document_version=document_version,
            chunk_type=chunk_type,
            chunk_index=chunk_index,
            content_hash=content_hash
        )
        chunk_ids.append(chunk_id)
        print(f"   Run {i+1}: {chunk_id}")
    
    # Verify all are identical
    print("\n[5] Verifying all chunk_ids are identical...")
    first_id = chunk_ids[0]
    all_identical = all(cid == first_id for cid in chunk_ids)
    
    if all_identical:
        print(f"   ✓ All 5 chunk_ids are identical")
        print(f"   ✓ Deterministic ID scheme confirmed")
    else:
        print(f"   ✗ Chunk IDs differ across runs:")
        for i, cid in enumerate(chunk_ids):
            print(f"     Run {i+1}: {cid}")
        return False
    
    # Test that different inputs produce different IDs
    print("\n[6] Verifying different inputs produce different chunk_ids...")
    
    # Change chunk_index
    chunk_id_different_index = generator.generate(
        tenant_id=tenant_id,
        document_id=document_id,
        document_version=document_version,
        chunk_type=chunk_type,
        chunk_index=1,  # Different
        content_hash=content_hash
    )
    
    # Change content_hash
    chunk_id_different_content = generator.generate(
        tenant_id=tenant_id,
        document_id=document_id,
        document_version=document_version,
        chunk_type=chunk_type,
        chunk_index=chunk_index,
        content_hash="different_hash_value"  # Different
    )
    
    # Change tenant_id
    chunk_id_different_tenant = generator.generate(
        tenant_id="tenant_002",  # Different
        document_id=document_id,
        document_version=document_version,
        chunk_type=chunk_type,
        chunk_index=chunk_index,
        content_hash=content_hash
    )
    
    print(f"   Original chunk_id: {first_id}")
    print(f"   Different chunk_index: {chunk_id_different_index}")
    print(f"   Different content_hash: {chunk_id_different_content}")
    print(f"   Different tenant_id: {chunk_id_different_tenant}")
    
    if (chunk_id_different_index != first_id and 
        chunk_id_different_content != first_id and 
        chunk_id_different_tenant != first_id):
        print(f"   ✓ Different inputs produce different chunk_ids")
    else:
        print(f"   ✗ Some different inputs produced same chunk_id")
        return False
    
    # Test that content hash is deterministic
    print("\n[7] Verifying content hash determinism...")
    content_hashes = []
    for i in range(5):
        h = generator.compute_content_hash(content_text)
        content_hashes.append(h)
    
    all_hashes_identical = all(h == content_hashes[0] for h in content_hashes)
    
    if all_hashes_identical:
        print(f"   ✓ All 5 content hashes are identical")
        print(f"   ✓ Content hash determinism confirmed")
    else:
        print(f"   ✗ Content hashes differ")
        return False
    
    # Verify ID format (SHA256 = 64 hex characters)
    print("\n[8] Verifying chunk_id format (SHA256 = 64 hex characters)...")
    if len(first_id) == 64:
        print(f"   ✓ Chunk ID length is 64 characters")
    else:
        print(f"   ✗ Chunk ID length is {len(first_id)}, expected 64")
        return False
    
    try:
        int(first_id, 16)
        print(f"   ✓ Chunk ID is valid hexadecimal")
    except ValueError:
        print(f"   ✗ Chunk ID is not valid hexadecimal")
        return False
    
    print("\n" + "=" * 80)
    print("COMPONENT 2 VERIFICATION: PASSED")
    print("=" * 80)
    print("\nEVIDENCE:")
    print(f"- 5 consecutive hash operations produced identical chunk_id: {first_id}")
    print(f"- Different inputs (chunk_index, content_hash, tenant_id) produce different IDs")
    print(f"- Content hash is deterministic across 5 runs: {content_hashes[0]}")
    print(f"- Chunk ID format is valid SHA256 (64 hex characters)")
    print(f"- No random UUIDs, auto-increment IDs, or timestamp-based hashes detected")
    
    return True


if __name__ == "__main__":
    try:
        success = verify_chunk_id_determinism()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
