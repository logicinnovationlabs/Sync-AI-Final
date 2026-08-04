"""
Sanity check: Test mock latency behavior (serial vs batched)
Per user request: verify whether mock latency is applied serially per document
or as one round-trip per batch.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.harness.throughput_harness import ThroughputHarness
from app.embeddings.mock_provider import MockEmbeddingProvider


async def check_latency_behavior():
    """Test throughput with different mock latencies to determine serial vs batched behavior."""
    
    print("=" * 80)
    print("MOCK LATENCY SANITY CHECK")
    print("=" * 80)
    
    latencies = [50, 100, 200]  # ms
    results = []
    
    for latency_ms in latencies:
        print(f"\n[TEST] Testing with base_latency_ms = {latency_ms}ms")
        
        # Create mock provider with specific latency
        provider = MockEmbeddingProvider(
            base_latency_ms=latency_ms,
            jitter_ms=0,  # No jitter for cleaner measurement
            vector_dimension=1536,
        )
        
        # Create harness with this provider
        harness = ThroughputHarness(embedding_provider=provider)
        
        # Run short test (10 docs)
        docs = harness.generate_test_documents(10, "prose")
        
        result = await harness.measure_end_to_end_throughput(docs, "prose")
        
        docs_per_min = result['docs_per_minute']
        docs_per_sec = docs_per_min / 60
        ms_per_doc = 1000 / docs_per_sec if docs_per_sec > 0 else 0
        
        print(f"   Docs/min: {docs_per_min:.1f}")
        print(f"   Docs/sec: {docs_per_sec:.1f}")
        print(f"   ms/doc: {ms_per_doc:.1f}")
        
        results.append({
            'latency_ms': latency_ms,
            'docs_per_min': docs_per_min,
            'ms_per_doc': ms_per_doc,
        })
    
    print("\n" + "=" * 80)
    print("LATENCY ANALYSIS")
    print("=" * 80)
    
    print(f"\n{'Latency (ms)':<15} {'Docs/min':<15} {'ms/doc':<15} {'Ratio to latency':<20}")
    print("-" * 80)
    
    for r in results:
        ratio = r['ms_per_doc'] / r['latency_ms'] if r['latency_ms'] > 0 else 0
        print(f"{r['latency_ms']:<15} {r['docs_per_min']:<15.1f} {r['ms_per_doc']:<15.1f} {ratio:<20.2f}")
    
    # Analyze behavior
    print("\n" + "=" * 80)
    print("INTERPRETATION")
    print("=" * 80)
    
    # Check if ms_per_doc scales linearly with latency (serial behavior)
    ratios = [r['ms_per_doc'] / r['latency_ms'] for r in results]
    avg_ratio = sum(ratios) / len(ratios)
    ratio_variance = max(ratios) - min(ratios)
    
    print(f"\nAverage ms/doc to latency ratio: {avg_ratio:.2f}")
    print(f"Ratio variance: {ratio_variance:.2f}")
    
    if ratio_variance < 0.5:
        print("\n✓ CONCLUSION: SERIAL PER-DOCUMENT LATENCY")
        print("  - ms_per_doc scales linearly with configured latency")
        print("  - Ratio is consistent (~1.0) across different latencies")
        print("  - Mock applies latency per document, not per batch")
        print("  - Throughput is mechanically capped by latency setting")
    else:
        print("\n✓ CONCLUSION: BATCHED LATENCY")
        print("  - ms_per_doc does NOT scale linearly with configured latency")
        print("  - Ratio varies significantly across different latencies")
        print("  - Mock applies latency per batch, not per document")
    
    print("\nNOTE: This behavior should be documented in SIGNOFF.md")


if __name__ == "__main__":
    try:
        asyncio.run(check_latency_behavior())
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
