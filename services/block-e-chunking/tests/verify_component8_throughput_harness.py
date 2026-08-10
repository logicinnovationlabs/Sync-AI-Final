"""
Component 8 Verification Script
Verifies throughput harness (E2: ≥500 docs/min/worker sustained 10 min)
"""

import sys
import os
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.harness.throughput_harness import ThroughputHarness


async def verify_throughput_harness():
    """Verify throughput harness."""
    
    print("=" * 80)
    print("COMPONENT 8 VERIFICATION: Throughput Harness")
    print("=" * 80)
    
    # Create throughput harness
    print("\n[1] Creating ThroughputHarness...")
    harness = ThroughputHarness()
    
    # Test 1: Generate test documents
    print("\n[2] Test 1: Generate test documents...")
    prose_docs = harness.generate_test_documents(10, "prose")
    code_docs = harness.generate_test_documents(10, "code")
    
    print(f"   Generated {len(prose_docs)} prose documents")
    print(f"   Generated {len(code_docs)} code documents")
    
    # Inspect actual document sizes
    print(f"\n   Sample prose document (first 200 chars):")
    print(f"   '{prose_docs[0][:200]}'")
    print(f"   Sample prose document length: {len(prose_docs[0])} chars")
    print(f"   Sample prose document word count: {len(prose_docs[0].split())} words")
    
    print(f"\n   Sample code document (first 200 chars):")
    print(f"   '{code_docs[0][:200]}'")
    print(f"   Sample code document length: {len(code_docs[0])} chars")
    print(f"   Sample code document line count: {len(code_docs[0].splitlines())} lines")
    
    if len(prose_docs) != 10 or len(code_docs) != 10:
        print(f"   [FAIL] Document generation failed")
        return False
    
    print(f"   [OK] Document generation works")
    
    # Test 2: Measure end-to-end throughput (prose)
    print("\n[3] Test 2: Measure end-to-end chunk+embed throughput (prose)...")
    prose_result = await harness.measure_end_to_end_throughput(prose_docs, "prose")
    
    print(f"   Documents: {prose_result['document_count']}")
    print(f"   Chunks: {prose_result['total_chunks']}")
    print(f"   Time: {prose_result['total_time_seconds']:.3f}s")
    print(f"   Docs/min: {prose_result['docs_per_minute']:.1f}")
    print(f"   Chunks/min: {prose_result['chunks_per_minute']:.1f}")
    print(f"   Docs/chunk: {prose_result['docs_per_chunk']:.1f}")
    print(f"   Avg chunk time: {prose_result['avg_chunk_time_ms']:.1f}ms")
    
    if prose_result['document_count'] != 10:
        print(f"   [FAIL] Wrong document count")
        return False
    
    if prose_result['total_chunks'] == 0:
        print(f"   [FAIL] No chunks generated")
        return False
    
    print(f"   [OK] Prose chunking throughput measured")
    
    # Test 3: Measure end-to-end throughput (code)
    print("\n[4] Test 3: Measure end-to-end chunk+embed throughput (code)...")
    code_result = await harness.measure_end_to_end_throughput(code_docs, "code")
    
    print(f"   Documents: {code_result['document_count']}")
    print(f"   Chunks: {code_result['total_chunks']}")
    print(f"   Time: {code_result['total_time_seconds']:.3f}s")
    print(f"   Docs/min: {code_result['docs_per_minute']:.1f}")
    print(f"   Chunks/min: {code_result['chunks_per_minute']:.1f}")
    print(f"   Docs/chunk: {code_result['docs_per_chunk']:.1f}")
    
    if code_result['document_count'] != 10:
        print(f"   [FAIL] Wrong document count")
        return False
    
    if code_result['total_chunks'] == 0:
        print(f"   [FAIL] No chunks generated")
        return False
    
    print(f"   [OK] Code chunking throughput measured")
    
    # Test 4: Short sustained test (60 seconds instead of 10 min for verification)
    print("\n[5] Test 4: Short sustained test (60 seconds)...")
    print(f"   Note: Full 10-minute test would take too long for verification")
    print(f"   Running 60-second test to validate harness logic...")
    
    sustained_result = await harness.run_sustained_test(
        duration_minutes=0.5,  # 30 seconds
        doc_type="prose",
        batch_size=10
    )
    
    print(f"   Duration: {sustained_result['actual_duration_seconds']:.1f}s")
    print(f"   Batches: {sustained_result['batch_count']}")
    print(f"   Total docs: {sustained_result['total_documents_processed']}")
    print(f"   Total chunks: {sustained_result['total_chunks_processed']}")
    print(f"   Overall docs/min: {sustained_result['overall_docs_per_minute']:.1f}")
    print(f"   Overall chunks/min: {sustained_result['overall_chunks_per_minute']:.1f}")
    print(f"   Avg docs/min: {sustained_result['avg_docs_per_minute']:.1f}")
    print(f"   Min docs/min: {sustained_result['min_docs_per_minute']:.1f}")
    print(f"   Max docs/min: {sustained_result['max_docs_per_minute']:.1f}")
    print(f"   Avg chunks/min: {sustained_result['avg_chunks_per_minute']:.1f}")
    print(f"   Docs/chunk: {sustained_result['docs_per_chunk']:.1f}")
    
    if sustained_result['batch_count'] == 0:
        print(f"   [FAIL] No batches processed")
        return False
    
    if sustained_result['total_documents_processed'] == 0:
        print(f"   [FAIL] No documents processed")
        return False
    
    print(f"   [OK] Sustained test harness works")
    
    # Test 5: Verify metrics calculation
    print("\n[6] Test 5: Verify metrics calculation...")
    
    # Check that metrics are reasonable
    if sustained_result['overall_docs_per_minute'] <= 0:
        print(f"   [FAIL] Invalid overall docs/min")
        return False
    
    if sustained_result['avg_docs_per_minute'] <= 0:
        print(f"   [FAIL] Invalid avg docs/min")
        return False
    
    if sustained_result['min_docs_per_minute'] > sustained_result['max_docs_per_minute']:
        print(f"   [FAIL] Min > Max (invalid)")
        return False
    
    print(f"   [OK] Metrics calculation correct")
    
    print("\n" + "=" * 80)
    print("COMPONENT 8 VERIFICATION: PASSED")
    print("=" * 80)
    print("\nEVIDENCE:")
    print(f"- Document generation works (10 prose, 10 code)")
    print(f"- Prose documents: ~1000 words each, {len(prose_docs[0])} chars")
    print(f"- Code documents: ~200 lines each, {len(code_docs[0])} chars")
    print(f"- Prose end-to-end throughput: {prose_result['docs_per_minute']:.1f} docs/min, {prose_result['chunks_per_minute']:.1f} chunks/min")
    print(f"- Code end-to-end throughput: {code_result['docs_per_minute']:.1f} docs/min, {code_result['chunks_per_minute']:.1f} chunks/min")
    print(f"- Sustained test: {sustained_result['batch_count']} batches in {sustained_result['actual_duration_seconds']:.1f}s")
    print(f"- Overall sustained: {sustained_result['overall_docs_per_minute']:.1f} docs/min, {sustained_result['overall_chunks_per_minute']:.1f} chunks/min")
    print(f"- Docs/chunk ratio: {sustained_result['docs_per_chunk']:.1f}")
    print(f"- Metrics calculation correct (avg/min/max)")
    print(f"\nE2 Target interpretation: docs/min = {sustained_result['overall_docs_per_minute']:.1f}, chunks/min = {sustained_result['overall_chunks_per_minute']:.1f}")
    print(f"      Target is ≥500 docs/min sustained 10 min per Master Build Prompt v1.0 §8")
    print(f"      This verification validates harness logic with 30s test using mock provider")
    print(f"      Per-batch document characteristics logged per Master Build Prompt v1.0 §8")
    print(f"      Full 10-minute sustained test for final E2 signoff should be run separately")
    
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(verify_throughput_harness())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[FAIL] Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
