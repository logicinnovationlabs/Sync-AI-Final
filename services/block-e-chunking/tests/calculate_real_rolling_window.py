"""
Calculate real 60-second rolling window from actual per-batch timestamped data
Per Master Build Prompt v2.0 §8.4: E2 requires empirical rolling window, not theoretical derivation
"""

import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.harness.throughput_harness import ThroughputHarness


async def calculate_real_rolling_window():
    """Calculate real 60-second rolling window from actual per-batch timestamped data."""
    
    print("=" * 80)
    print("E2 REAL ROLLING WINDOW CALCULATION (v2.0 §8.4)")
    print("=" * 80)
    
    # Create throughput harness
    print("\n[1] Creating ThroughputHarness with MockEmbeddingProvider...")
    harness = ThroughputHarness()
    
    # Run 10-minute sustained test with timestamp capture
    print("\n[2] Running 10-minute sustained test with timestamp capture...")
    print("   This will take approximately 10 minutes to complete.")
    
    sustained_result = await harness.run_sustained_test(
        duration_minutes=10,
        doc_type="prose",
        batch_size=10
    )
    
    print("\n[3] Extracting batch timestamped data...")
    batch_timestamps = sustained_result.get('batch_timestamps', [])
    
    if not batch_timestamps:
        print("   ✗ No batch timestamps found in result")
        return False
    
    print(f"   Total batches: {len(batch_timestamps)}")
    print(f"   First batch timestamp: {batch_timestamps[0][0]:.2f}")
    print(f"   Last batch timestamp: {batch_timestamps[-1][0]:.2f}")
    
    # Calculate 60-second rolling window averages
    print("\n[4] Calculating 60-second rolling window averages...")
    
    window_size_seconds = 60
    rolling_window_averages = []
    
    for i, (timestamp, doc_count) in enumerate(batch_timestamps):
        # Find all batches within 60 seconds before this batch
        window_start = timestamp - window_size_seconds
        window_docs = sum(dc for ts, dc in batch_timestamps if window_start <= ts <= timestamp)
        window_duration = timestamp - max(window_start, batch_timestamps[0][0])
        
        if window_duration > 0:
            docs_per_minute = (window_docs / window_duration) * 60
            rolling_window_averages.append(docs_per_minute)
            
            if i == 0 or i == len(batch_timestamps) - 1 or i % 100 == 0:
                print(f"   Batch {i+1}: {docs_per_minute:.1f} docs/min (window: {window_duration:.1f}s, docs: {window_docs})")
    
    # Find worst rolling window
    worst_rolling_window = min(rolling_window_averages) if rolling_window_averages else 0
    best_rolling_window = max(rolling_window_averages) if rolling_window_averages else 0
    avg_rolling_window = sum(rolling_window_averages) / len(rolling_window_averages) if rolling_window_averages else 0
    
    print("\n[5] Rolling window statistics:")
    print(f"   Worst 60-second rolling window: {worst_rolling_window:.1f} docs/min")
    print(f"   Best 60-second rolling window: {best_rolling_window:.1f} docs/min")
    print(f"   Average 60-second rolling window: {avg_rolling_window:.1f} docs/min")
    
    print("\n[6] v2.0 §8.4 threshold check:")
    print(f"   Part 1: Aggregate throughput = {sustained_result['overall_docs_per_minute']:.1f} docs/min ≥ 500")
    print(f"   Result: {sustained_result['overall_docs_per_minute']:.1f} ≥ 500 → {'PASS' if sustained_result['overall_docs_per_minute'] >= 500 else 'FAIL'}")
    print(f"   Part 2: Worst 60-second rolling window = {worst_rolling_window:.1f} docs/min ≥ 400")
    print(f"   Result: {worst_rolling_window:.1f} ≥ 400 → {'PASS' if worst_rolling_window >= 400 else 'FAIL'}")
    
    # Save batch timestamps for later analysis
    print("\n[7] Saving batch timestamped data...")
    with open('batch_timestamps.json', 'w') as f:
        json.dump({
            'batch_timestamps': batch_timestamps,
            'rolling_window_averages': rolling_window_averages,
            'worst_rolling_window': worst_rolling_window,
            'best_rolling_window': best_rolling_window,
            'avg_rolling_window': avg_rolling_window,
        }, f, indent=2)
    print(f"   Data saved to batch_timestamps.json")
    
    print("\n" + "=" * 80)
    if sustained_result['overall_docs_per_minute'] >= 500 and worst_rolling_window >= 400:
        print("E2 VERIFICATION: PASS (v2.0 §8.4 two-part threshold)")
        print("=" * 80)
        print("\nEVIDENCE:")
        print(f"- Aggregate throughput: {sustained_result['overall_docs_per_minute']:.1f} docs/min ≥ 500 → PASS")
        print(f"- Worst 60-second rolling window: {worst_rolling_window:.1f} docs/min ≥ 400 → PASS")
        print(f"- Rolling window calculated from {len(batch_timestamps)} actual timestamped batches")
        print(f"- Empirical data, not theoretical derivation")
        return True
    else:
        print("E2 VERIFICATION: FAIL")
        print("=" * 80)
        print("\nEVIDENCE:")
        print(f"- Aggregate throughput: {sustained_result['overall_docs_per_minute']:.1f} docs/min ≥ 500 → {'PASS' if sustained_result['overall_docs_per_minute'] >= 500 else 'FAIL'}")
        print(f"- Worst 60-second rolling window: {worst_rolling_window:.1f} docs/min ≥ 400 → {'PASS' if worst_rolling_window >= 400 else 'FAIL'}")
        print(f"- Rolling window calculated from {len(batch_timestamps)} actual timestamped batches")
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(calculate_real_rolling_window())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Calculation failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
