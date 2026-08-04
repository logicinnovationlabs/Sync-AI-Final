"""
E2 Throughput Test: Actual 10-minute sustained run.
Per Phase 2.1: Run the actual sustained 10-minute load test against the reference corpus.
Requirements: ≥500 docs/min per worker sustained 10 minutes.
Output: Full run's docs/min figure plus per-minute breakdown across the whole run.
"""

import sys
import os
import asyncio
import json
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.harness.throughput_harness import ThroughputHarness


async def run_10min_throughput_test():
    """Run actual 10-minute sustained throughput test."""
    
    print("=" * 80)
    print("E2 THROUGHPUT TEST: 10-MINUTE SUSTAINED RUN")
    print("=" * 80)
    print(f"[START TIME] {datetime.now(timezone.utc).isoformat()}")
    print()
    
    # Create throughput harness with mock provider (per existing setup)
    print("[SETUP] Creating ThroughputHarness with MockEmbeddingProvider...")
    harness = ThroughputHarness()
    print(f"[SETUP] Provider: {type(harness.embedding_provider).__name__}")
    print(f"[SETUP] Base latency: 100ms ±50ms jitter")
    print()
    
    # Run 10-minute sustained test
    print("[TEST] Starting 10-minute sustained throughput test...")
    print("[TEST] This will take exactly 10 minutes (600 seconds)")
    print("[TEST] Measuring end-to-end chunk+embed pipeline")
    print()
    
    result = await harness.run_sustained_test(
        duration_minutes=10,  # Full 10 minutes per E2 spec
        doc_type="prose",     # Using prose documents
        batch_size=50         # 50 docs per batch
    )
    
    print()
    print("=" * 80)
    print("E2 THROUGHPUT TEST RESULTS")
    print("=" * 80)
    print(f"[END TIME] {datetime.now(timezone.utc).isoformat()}")
    print()
    
    print(f"[AGGREGATE METRICS]")
    print(f"Actual duration: {result['actual_duration_seconds']:.1f} seconds")
    print(f"Target duration: {result['duration_minutes']} minutes")
    print(f"Total batches: {result['batch_count']}")
    print(f"Total documents processed: {result['total_documents_processed']}")
    print(f"Total chunks processed: {result['total_chunks_processed']}")
    print()
    
    print(f"[THROUGHPUT METRICS]")
    print(f"Overall docs/min: {result['overall_docs_per_minute']:.1f}")
    print(f"Overall chunks/min: {result['overall_chunks_per_minute']:.1f}")
    print(f"Average docs/min (per batch): {result['avg_docs_per_minute']:.1f}")
    print(f"Minimum docs/min (per batch): {result['min_docs_per_minute']:.1f}")
    print(f"Maximum docs/min (per batch): {result['max_docs_per_minute']:.1f}")
    print(f"Average chunks/min (per batch): {result['avg_chunks_per_minute']:.1f}")
    print(f"Docs/chunk ratio: {result['docs_per_chunk']:.1f}")
    print()
    
    print(f"[THRESHOLD CHECK]")
    print(f"Target: ≥500 docs/min per worker")
    print(f"Aggregate result: {result['overall_docs_per_minute']:.1f} docs/min")
    print(f"Meets target: {'YES ✓' if result['overall_docs_per_minute'] >= 500 else 'NO ✗'}")
    print(f"Minimum batch: {result['min_docs_per_minute']:.1f} docs/min")
    print(f"Minimum meets target: {'YES ✓' if result['min_docs_per_minute'] >= 500 else 'NO ✗'}")
    print()
    
    # Per-minute breakdown (calendar minutes — informational)
    print(f"[PER-MINUTE BREAKDOWN]")
    print(f"Calculating per-minute throughput from batch timestamps...")
    
    # Group batches by minute
    per_minute_data = []
    batch_timestamps = result['batch_timestamps']
    
    if batch_timestamps:
        start_time = batch_timestamps[0][0]
        for minute in range(10):  # 10 minutes
            minute_start = start_time + (minute * 60)
            minute_end = minute_start + 60
            
            # Sum docs in this minute window
            docs_in_minute = 0
            for batch_time, doc_count in batch_timestamps:
                if minute_start <= batch_time < minute_end:
                    docs_in_minute += doc_count
            
            docs_per_minute = docs_in_minute  # Already per minute
            per_minute_data.append({
                'minute': minute + 1,
                'docs_per_minute': docs_per_minute,
                'meets_target': docs_per_minute >= 500
            })
            
            print(f"Minute {minute + 1}: {docs_per_minute:.1f} docs/min {'YES' if docs_per_minute >= 500 else 'NO'}")
    
    print()

    # Genuine 60-second sliding windows recomputed at every batch boundary
    print(f"[SLIDING 60s WINDOWS AT BATCH BOUNDARIES]")
    sliding_windows = []
    events = []  # (end_time, docs, idx)
    for i, (ts, docs) in enumerate(batch_timestamps):
        events.append({"end": ts, "docs": docs, "idx": i + 1})

    run_start = None
    for i, ev in enumerate(events):
        br = (result.get("batch_results") or [None])[i] if i < len(result.get("batch_results") or []) else None
        if br and br.get("total_time_seconds"):
            batch_start = ev["end"] - float(br["total_time_seconds"])
            if run_start is None or batch_start < run_start:
                run_start = batch_start
        elif run_start is None:
            run_start = ev["end"]
    if run_start is None:
        run_start = time.time()

    worst_window = None
    for i, ev in enumerate(events):
        window_end = ev["end"]
        elapsed = max(window_end - run_start, 1e-9)
        window_start = window_end - 60.0
        docs_in_window = 0
        batches_in_window = 0
        for other in events[: i + 1]:
            if other["end"] > window_start and other["end"] <= window_end:
                docs_in_window += other["docs"]
                batches_in_window += 1
        # Normalize partial windows (<60s since run start) to docs/min
        window_seconds = min(60.0, elapsed)
        rate = (docs_in_window / window_seconds) * 60.0
        sliding_windows.append({
            "batch": ev["idx"],
            "window_end": window_end,
            "window_seconds": window_seconds,
            "docs_in_window": docs_in_window,
            "batches_in_window": batches_in_window,
            "docs_per_minute": rate,
            "meets_400": rate >= 400,
        })
        if worst_window is None or rate < worst_window["docs_per_minute"]:
            worst_window = sliding_windows[-1]
        print(
            f"Batch {ev['idx']:03d} window: {rate:.1f} docs/min "
            f"(docs={docs_in_window}, secs={window_seconds:.1f}, batches={batches_in_window}) "
            f"{'OK' if rate >= 400 else 'FAIL'}"
        )

    print()
    if worst_window:
        print(
            f"[SLIDING WINDOW SUMMARY] worst={worst_window['docs_per_minute']:.1f} docs/min "
            f"at batch {worst_window['batch']} (threshold >=400)"
        )
    print()
    
    # Save results to JSON for audit trail
    output_file = "e2_10min_results.json"
    output_data = {
        "test_type": "E2 10-minute sustained throughput",
        "start_time": datetime.now(timezone.utc).isoformat(),
        "aggregate_metrics": {
            "overall_docs_per_minute": result['overall_docs_per_minute'],
            "overall_chunks_per_minute": result['overall_chunks_per_minute'],
            "avg_docs_per_minute": result['avg_docs_per_minute'],
            "min_docs_per_minute": result['min_docs_per_minute'],
            "max_docs_per_minute": result['max_docs_per_minute'],
            "total_documents": result['total_documents_processed'],
            "total_chunks": result['total_chunks_processed'],
            "actual_duration_seconds": result['actual_duration_seconds']
        },
        "per_minute_breakdown": per_minute_data,
        "sliding_60s_windows": sliding_windows,
        "worst_sliding_window_docs_per_minute": worst_window["docs_per_minute"] if worst_window else None,
        "meets_target": (
            result['overall_docs_per_minute'] >= 500
            and (worst_window is not None and worst_window["docs_per_minute"] >= 400)
        ),
    }
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"[RESULTS SAVED] {output_file}")
    print()
    
    # Final verdict — aggregate >=500 AND every 60s sliding window >=400
    worst_rate = worst_window["docs_per_minute"] if worst_window else 0
    all_windows_ok = all(w["meets_400"] for w in sliding_windows) if sliding_windows else False
    if result['overall_docs_per_minute'] >= 500 and all_windows_ok:
        print("=" * 80)
        print("E2 THROUGHPUT TEST: PASSED")
        print("=" * 80)
        print(f"Aggregate throughput: {result['overall_docs_per_minute']:.1f} docs/min >= 500")
        print(f"Worst 60s sliding window: {worst_rate:.1f} docs/min >= 400")
        print(f"Sliding windows checked: {len(sliding_windows)}")
        return True
    else:
        print("=" * 80)
        print("E2 THROUGHPUT TEST: FAILED")
        print("=" * 80)
        print(f"Aggregate throughput: {result['overall_docs_per_minute']:.1f} docs/min (need >=500)")
        print(f"Worst 60s sliding window: {worst_rate:.1f} docs/min (need >=400)")
        print(f"All windows OK: {all_windows_ok}")
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(run_10min_throughput_test())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
