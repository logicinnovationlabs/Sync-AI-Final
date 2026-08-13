"""
Block I Signoff Tests: Activity Signals Service

Tests I1-I3 per signoff requirements:
- I1: Privacy threshold enforcement
- I2: Retention enforcement
- I3: Signal freshness p95 <= 15m
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest

# Test configuration
TEST_TENANT = "block-i-test"
PRIVACY_THRESHOLD = 5


@pytest.fixture
async def activity_store():
    """Get mock activity store for Phase 1 testing."""
    from app.services.signals.mock_store import MockActivityStore
    from app.models.activity import ActivityConfig
    
    store = MockActivityStore()
    
    # Configure test tenant
    config = ActivityConfig(
        tenant_id=TEST_TENANT,
        privacy_threshold=PRIVACY_THRESHOLD,
        retention_days=90,
        high_privacy_retention_days=30,
    )
    await store.ensure_tenant(TEST_TENANT, config)
    await store.set_config(config)
    
    yield store
    
    await store.clear_tenant(TEST_TENANT)


@pytest.mark.asyncio
async def test_i1_privacy_threshold(activity_store):
    """
    I1: Privacy Threshold Enforcement
    
    Test that document signals are privacy-protected when actor count < threshold.
    Expected: 4/4 test cases pass (1, 3, 5, 10 actors).
    """
    print("\n[SIGNOFF I1] Privacy Threshold Test")
    print("=" * 60)
    
    from app.models.activity import ActivityEvent
    
    test_cases = [
        {"actors": 1, "protected": True},
        {"actors": 3, "protected": True},
        {"actors": 5, "protected": False},
        {"actors": 10, "protected": False},
    ]
    
    passed = 0
    
    for case in test_cases:
        doc_id = f"doc-{case['actors']}-actors"
        actor_count = case["actors"]
        should_protect = case["protected"]
        
        # Ingest events from N distinct actors
        for i in range(actor_count):
            event = ActivityEvent(
                event_id=f"{doc_id}-view-{i}",
                actor_principal_id=f"user-{i}",
                object_id=doc_id,
                event_type="view",
                source_system="test",
                event_time=datetime.now(timezone.utc),
            )
            await activity_store.ingest_event(TEST_TENANT, event)
        
        # Query document signals
        signals = await activity_store.get_document_signals(TEST_TENANT, doc_id)
        
        print(f"\nTest case: {actor_count} actors")
        print(f"  Document ID: {doc_id}")
        print(f"  Privacy protected: {signals.privacy_protected}")
        print(f"  Expected protected: {should_protect}")
        print(f"  Total views: {signals.total_views}")
        print(f"  Distinct viewers: {signals.distinct_viewers}")
        
        if should_protect:
            # Should be protected (null numerics)
            if signals.privacy_protected and signals.total_views is None:
                print(f"  [OK] Correctly privacy-protected")
                passed += 1
            else:
                print(f"  [FAIL] Should be protected but got: {signals}")
        else:
            # Should NOT be protected (numeric values present)
            if not signals.privacy_protected and signals.total_views == actor_count:
                print(f"  [OK] Correctly showing metrics")
                passed += 1
            else:
                print(f"  [FAIL] Should show metrics but got: {signals}")
    
    print(f"\n[RESULT] I1: {passed}/{len(test_cases)} test cases passed")
    
    if passed == len(test_cases):
        print("[PASS] I1: Privacy threshold correctly enforced")
    else:
        assert False, f"Privacy threshold failed: {passed}/{len(test_cases)} passed"
    
    assert passed == len(test_cases)


@pytest.mark.asyncio
async def test_i2_retention_enforcement(activity_store):
    """
    I2: Retention Enforcement
    
    Test that expired events are purged and active events are retained.
    Expected: All expired events purged, active events retained.
    """
    print("\n[SIGNOFF I2] Retention Enforcement Test")
    print("=" * 60)
    
    from app.models.activity import ActivityEvent
    
    now = datetime.now(timezone.utc)
    
    # Create events with different TTLs
    # Expired events (TTL 1 second, ingested 2 seconds ago)
    expired_events = []
    for i in range(8):
        event = ActivityEvent(
            event_id=f"expired-event-{i}",
            actor_principal_id=f"user-{i}",
            object_id=f"doc-{i}",
            event_type="view",
            source_system="test",
            event_time=now,
            ttl_seconds=1,  # 1 second TTL
        )
        # Manually set ingested_at to 2 seconds ago for testing
        await activity_store.ingest_event(TEST_TENANT, event, ingested_at=now - timedelta(seconds=2))
        expired_events.append(event.event_id)
    
    # Active events (TTL 3600 seconds)
    active_events = []
    for i in range(5):
        event = ActivityEvent(
            event_id=f"active-event-{i}",
            actor_principal_id=f"user-{i}",
            object_id=f"doc-{i}",
            event_type="edit",
            source_system="test",
            event_time=now,
            ttl_seconds=3600,  # Still active
        )
        await activity_store.ingest_event(TEST_TENANT, event)
        active_events.append(event.event_id)
    
    print(f"\nCreated {len(expired_events)} expired events")
    print(f"Created {len(active_events)} active events")
    
    # Run purge
    print("\nRunning retention purge...")
    result = await activity_store.purge_expired(now=now)
    
    print(f"  Purged events: {result.purged_events}")
    print(f"  Expected purged: {len(expired_events)}")
    
    # Verify expired events are gone
    remaining_expired = 0
    for event_id in expired_events:
        stored = await activity_store.get_event(TEST_TENANT, event_id)
        if stored is not None:
            remaining_expired += 1
    
    # Verify active events remain
    remaining_active = 0
    for event_id in active_events:
        stored = await activity_store.get_event(TEST_TENANT, event_id)
        if stored is not None:
            remaining_active += 1
    
    print(f"\nAfter purge:")
    print(f"  Expired events remaining: {remaining_expired}/{len(expired_events)} (should be 0)")
    print(f"  Active events remaining: {remaining_active}/{len(active_events)} (should be {len(active_events)})")
    
    if remaining_expired == 0 and remaining_active == len(active_events):
        print(f"\n[PASS] I2: Retention correctly enforced ({result.purged_events} purged)")
    else:
        assert False, f"Retention failed: {remaining_expired} expired events not purged"
    
    assert remaining_expired == 0
    assert remaining_active == len(active_events)


@pytest.mark.asyncio
async def test_i3_signal_freshness(activity_store):
    """
    I3: Signal Freshness p95 <= 15 minutes
    
    Measure latency from event ingestion to signal query.
    Expected: p95 <= 900 seconds (15 minutes).
    """
    print("\n[SIGNOFF I3] Signal Freshness Test")
    print("=" * 60)
    
    from app.models.activity import ActivityEvent
    
    n_probes = 20
    latencies = []
    
    print(f"\nRunning {n_probes} ingest->query probes...")
    
    for i in range(n_probes):
        user_id = f"probe-user-{i}"
        doc_id = f"probe-doc-{i}"
        
        # Ingest event
        event = ActivityEvent(
            event_id=f"probe-event-{i}",
            actor_principal_id=user_id,
            object_id=doc_id,
            event_type="view",
            source_system="test",
            event_time=datetime.now(timezone.utc),
        )
        
        ingest_start = time.perf_counter()
        await activity_store.ingest_event(TEST_TENANT, event)
        
        # Query signals immediately
        signals = await activity_store.get_user_signals(TEST_TENANT, user_id)
        query_end = time.perf_counter()
        
        latency = query_end - ingest_start
        latencies.append(latency)
        
        if (i + 1) % 5 == 0:
            print(f"  Progress: {i + 1}/{n_probes}")
    
    # Calculate p95
    latencies.sort()
    p95_idx = min(len(latencies) - 1, int(len(latencies) * 0.95))
    p95 = latencies[p95_idx]
    avg = sum(latencies) / len(latencies)
    
    threshold_seconds = 900  # 15 minutes
    
    print(f"\nLatency stats:")
    print(f"  Samples: {len(latencies)}")
    print(f"  Average: {avg:.4f} seconds")
    print(f"  p95: {p95:.4f} seconds")
    print(f"  Threshold: {threshold_seconds} seconds (15 minutes)")
    
    if p95 <= threshold_seconds:
        print(f"\n[PASS] I3: p95 = {p95:.4f}s <= {threshold_seconds}s")
    else:
        print(f"\n[FAIL] I3: p95 = {p95:.4f}s > {threshold_seconds}s")
        assert False, f"Signal freshness p95 {p95:.4f}s exceeds {threshold_seconds}s threshold"
    
    assert p95 <= threshold_seconds


if __name__ == "__main__":
    print("\nBlock I Signoff Tests")
    print("=" * 60)
    print("Run with: pytest backend/tests/test_block_i_signoff.py -v -s")
