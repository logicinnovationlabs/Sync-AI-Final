"""
E2 Throughput Test: Actual 10-minute sustained run against real or mock provider.
Set EMBEDDING_PROVIDER=gemini and GEMINI_API_KEY for Phase 2.
"""

import sys
import os
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.harness.throughput_harness import ThroughputHarness
from app.embeddings.factory import create_embedding_provider


async def run_10min_throughput_test():
    print("=" * 80)
    print("E2 THROUGHPUT TEST: 10-MINUTE SUSTAINED RUN")
    print("=" * 80)
    print(f"[START TIME] {datetime.now(timezone.utc).isoformat()}")
    print()

    provider_name = (os.environ.get("EMBEDDING_PROVIDER") or "mock").strip().lower()
    print(f"[SETUP] EMBEDDING_PROVIDER={provider_name}")
    print(f"[SETUP] EMBEDDING_MODEL={os.environ.get('EMBEDDING_MODEL')}")
    print(f"[SETUP] EMBEDDING_DIMENSION={os.environ.get('EMBEDDING_DIMENSION') or os.environ.get('EMBEDDING_DIMENSIONS')}")
    print(f"[SETUP] FIXTURES_PATH={os.environ.get('FIXTURES_PATH')}")
    print(f"[SETUP] E2_DOC_CONCURRENCY={os.environ.get('E2_DOC_CONCURRENCY', '1')}")
    print(f"[SETUP] E2_BATCH_SIZE={os.environ.get('E2_BATCH_SIZE', '50')}")

    provider = create_embedding_provider()
    harness = ThroughputHarness(embedding_provider=provider)
    print(f"[SETUP] Provider class: {type(harness.embedding_provider).__name__}")
    print()

    duration = int(os.environ.get("E2_DURATION_MINUTES", "10"))
    batch_size = int(os.environ.get("E2_BATCH_SIZE", "50"))
    model_version = os.environ.get("EMBEDDING_MODEL") or "gemini-embedding-001"

    print(f"[TEST] Starting {duration}-minute sustained throughput test...")
    print(f"[TEST] model_version={model_version}")
    print()

    # Monkey-patch default model_version used inside measure by wrapping call
    original_measure = harness.measure_end_to_end_throughput

    async def measure_with_model(documents, doc_type="prose", tenant_id="test_tenant", model_version=model_version):
        return await original_measure(documents, doc_type=doc_type, tenant_id=tenant_id, model_version=model_version)

    harness.measure_end_to_end_throughput = measure_with_model

    result = await harness.run_sustained_test(
        duration_minutes=duration,
        doc_type="prose",
        batch_size=batch_size,
    )

    print()
    print("=" * 80)
    print("E2 THROUGHPUT TEST RESULTS")
    print("=" * 80)
    print(f"[END TIME] {datetime.now(timezone.utc).isoformat()}")
    print()
    print(f"[AGGREGATE METRICS]")
    print(f"Actual duration: {result['actual_duration_seconds']:.1f} seconds")
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
    print()

    throttle = getattr(provider, "throttle_events", 0)
    api_calls = getattr(provider, "total_api_calls", None)
    last_lat = getattr(provider, "last_batch_latency_ms", None)
    print(f"[PROVIDER STATS] throttle_events={throttle} total_api_calls={api_calls} last_batch_latency_ms={last_lat}")
    print()

    print(f"[THRESHOLD CHECK]")
    print(f"Target: >=500 docs/min per worker")
    print(f"Aggregate result: {result['overall_docs_per_minute']:.1f} docs/min")
    print(f"Meets target: {'YES' if result['overall_docs_per_minute'] >= 500 else 'NO'}")
    print()

    batch_timestamps = result["batch_timestamps"]
    sliding_windows = []
    events = [{"end": ts, "docs": docs, "idx": i + 1} for i, (ts, docs) in enumerate(batch_timestamps)]
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
        for other in events[: i + 1]:
            if other["end"] > window_start and other["end"] <= window_end:
                docs_in_window += other["docs"]
        window_seconds = min(60.0, elapsed)
        rate = (docs_in_window / window_seconds) * 60.0
        sliding_windows.append({"batch": ev["idx"], "docs_per_minute": rate, "meets_400": rate >= 400})
        if worst_window is None or rate < worst_window["docs_per_minute"]:
            worst_window = sliding_windows[-1]

    worst_rate = worst_window["docs_per_minute"] if worst_window else 0
    all_windows_ok = all(w["meets_400"] for w in sliding_windows) if sliding_windows else False
    print(f"[SLIDING WINDOW] worst={worst_rate:.1f} docs/min (need >=400) all_ok={all_windows_ok}")

    evidence_dir = SERVICE_ROOT / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    output_file = evidence_dir / "e2_phase2_gemini_10min_results.json"
    output_data = {
        "test_type": "E2 Phase2 Gemini 10-minute sustained throughput",
        "provider": type(provider).__name__,
        "model": os.environ.get("EMBEDDING_MODEL"),
        "dimension": os.environ.get("EMBEDDING_DIMENSION") or os.environ.get("EMBEDDING_DIMENSIONS"),
        "fixtures_path": os.environ.get("FIXTURES_PATH"),
        "concurrency": os.environ.get("E2_DOC_CONCURRENCY", "1"),
        "batch_size": batch_size,
        "duration_minutes": duration,
        "aggregate_metrics": {
            "overall_docs_per_minute": result["overall_docs_per_minute"],
            "min_docs_per_minute": result["min_docs_per_minute"],
            "max_docs_per_minute": result["max_docs_per_minute"],
            "total_documents": result["total_documents_processed"],
            "total_chunks": result["total_chunks_processed"],
            "actual_duration_seconds": result["actual_duration_seconds"],
        },
        "provider_stats": {
            "throttle_events": throttle,
            "total_api_calls": api_calls,
        },
        "worst_sliding_window_docs_per_minute": worst_rate,
        "meets_target": result["overall_docs_per_minute"] >= 500 and all_windows_ok,
        "ended_at": datetime.now(timezone.utc).isoformat(),
    }
    output_file.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    print(f"[RESULTS SAVED] {output_file}")

    if result["overall_docs_per_minute"] >= 500 and all_windows_ok:
        print("E2 THROUGHPUT TEST: PASSED")
        return True
    print("E2 THROUGHPUT TEST: FAILED")
    return False


if __name__ == "__main__":
    try:
        success = asyncio.run(run_10min_throughput_test())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nTest failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
