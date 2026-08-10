"""
Verification script for E4: Idempotency - identical chunk_id across reprocessing runs.

Tests that ChunkIDGenerator produces deterministic chunk_ids across 3 reprocessing runs
per v7.0 §4.5 (idempotency requirement).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chunkers.code_chunker import CodeChunker


def test_e4_idempotency():
    """Test that chunk_ids are identical across 3 reprocessing runs."""
    
    print("=" * 80)
    print("E4 IDEMPOTENCY VERIFICATION (v7.0 §4.5)")
    print("=" * 80)
    
    chunker = CodeChunker()
    
    # Fixture: A simple Python class
    test_source = """
class MyClass:
    def __init__(self, value):
        self.value = value
    
    def compute(self, x, y):
        return x + y + self.value
"""
    
    tenant_id = "test_tenant"
    document_id = "test_doc_001"
    document_version = "1"
    language = 'python'
    chunker_version = "1.0.0"
    
    # Run 1
    print("\n[1] Running first processing...")
    chunks_1 = chunker.chunk_with_metadata(
        tenant_id=tenant_id,
        document_id=document_id,
        document_version=document_version,
        source=test_source,
        language=language,
        chunker_version=chunker_version
    )
    chunk_ids_1 = {c['chunk_id'] for c in chunks_1}
    print(f"   Generated {len(chunks_1)} chunks")
    print(f"   Chunk IDs: {sorted(chunk_ids_1)}")
    
    # Run 2
    print("\n[2] Running second processing...")
    chunks_2 = chunker.chunk_with_metadata(
        tenant_id=tenant_id,
        document_id=document_id,
        document_version=document_version,
        source=test_source,
        language=language,
        chunker_version=chunker_version
    )
    chunk_ids_2 = {c['chunk_id'] for c in chunks_2}
    print(f"   Generated {len(chunks_2)} chunks")
    print(f"   Chunk IDs: {sorted(chunk_ids_2)}")
    
    # Run 3
    print("\n[3] Running third processing...")
    chunks_3 = chunker.chunk_with_metadata(
        tenant_id=tenant_id,
        document_id=document_id,
        document_version=document_version,
        source=test_source,
        language=language,
        chunker_version=chunker_version
    )
    chunk_ids_3 = {c['chunk_id'] for c in chunks_3}
    print(f"   Generated {len(chunks_3)} chunks")
    print(f"   Chunk IDs: {sorted(chunk_ids_3)}")
    
    # Verify all three runs produced identical chunk_ids
    print("\n[4] Verifying chunk_id consistency across runs...")
    
    if chunk_ids_1 == chunk_ids_2 == chunk_ids_3:
        print("   ✓ All three runs produced identical chunk_ids")
    else:
        print("   ✗ Chunk_ids differ across runs")
        print(f"   Run 1: {sorted(chunk_ids_1)}")
        print(f"   Run 2: {sorted(chunk_ids_2)}")
        print(f"   Run 3: {sorted(chunk_ids_3)}")
        return False
    
    # Verify chunk count is consistent
    if len(chunks_1) == len(chunks_2) == len(chunks_3):
        print(f"   ✓ All three runs produced {len(chunks_1)} chunks (consistent)")
    else:
        print("   ✗ Chunk count differs across runs")
        print(f"   Run 1: {len(chunks_1)} chunks")
        print(f"   Run 2: {len(chunks_2)} chunks")
        print(f"   Run 3: {len(chunks_3)} chunks")
        return False
    
    # Verify chunk content is consistent
    print("\n[5] Verifying chunk content consistency across runs...")
    for i in range(len(chunks_1)):
        if chunks_1[i]['chunk_text'] != chunks_2[i]['chunk_text'] or chunks_1[i]['chunk_text'] != chunks_3[i]['chunk_text']:
            print(f"   ✗ Chunk {i} content differs across runs")
            return False
    print("   ✓ All chunk content is identical across runs")
    
    # Verify chunk_id changes when content changes
    print("\n[6] Verifying chunk_id changes when content changes...")
    modified_source = test_source + "\n    def new_method(self):\n        return 42\n"
    chunks_modified = chunker.chunk_with_metadata(
        tenant_id=tenant_id,
        document_id=document_id,
        document_version=document_version,
        source=modified_source,
        language=language,
        chunker_version=chunker_version
    )
    chunk_ids_modified = {c['chunk_id'] for c in chunks_modified}
    
    if chunk_ids_modified != chunk_ids_1:
        print("   ✓ Chunk_ids changed when content changed (correct behavior)")
    else:
        print("   ✗ Chunk_ids did NOT change when content changed (incorrect)")
        return False
    
    # Verify chunk_id changes when chunker_version changes
    print("\n[7] Verifying chunk_id changes when chunker_version changes...")
    chunks_version_2 = chunker.chunk_with_metadata(
        tenant_id=tenant_id,
        document_id=document_id,
        document_version=document_version,
        source=test_source,
        language=language,
        chunker_version="2.0.0"
    )
    chunk_ids_version_2 = {c['chunk_id'] for c in chunks_version_2}
    
    if chunk_ids_version_2 != chunk_ids_1:
        print("   ✓ Chunk_ids changed when chunker_version changed (correct behavior)")
    else:
        print("   ✗ Chunk_ids did NOT change when chunker_version changed (incorrect)")
        return False
    
    print("\n" + "=" * 80)
    print("E4 IDEMPOTENCY VERIFICATION: PASSED")
    print("=" * 80)
    print("\nEVIDENCE:")
    print("- 3 reprocessing runs produced identical chunk_ids")
    print("- Chunk count consistent across runs")
    print("- Chunk content identical across runs")
    print("- Chunk_ids change when content changes (correct)")
    print("- Chunk_ids change when chunker_version changes (correct)")
    print("- ChunkIDGenerator is deterministic: SHA256(tenant_id | document_id | document_version | chunker_version | chunk_type | chunk_index | content_hash)")
    
    return True


if __name__ == "__main__":
    try:
        success = test_e4_idempotency()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
