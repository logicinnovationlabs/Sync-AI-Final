"""Block I Signoff Tests: Activity Signals Service (I1-I3)"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio

TEST_TENANT = "block-i-test"
PRIVACY_THRESHOLD = 5
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "block_z"


@pytest_asyncio.fixture
async def activity_store():
    """Always use real PostgreSQL – raises ConnectionError if unavailable."""
    from app.services.signals import get_activity_store
    from app.models.activity import ActivityConfig
    
    print("\n[BLOCK I] Forcing real PostgreSQL backend for signals...")
    
    try:
        store = get_activity_store()
        
        # Attempt to ensure a test tenant (this will connect to PostgreSQL)
        config = ActivityConfig(
            tenant_id=TEST_TENANT,
            privacy_threshold=PRIVACY_THRESHOLD,
            retention_days=90,
            high_privacy_retention_days=30,
        )
        await store.ensure_tenant(TEST_TENANT, config)
        await store.set_config(config)
        print("[BLOCK I] OK PostgreSQL reachable, tenant configured")
    except Exception as e:
        raise ConnectionError(f"PostgreSQL not reachable: {e}")

    yield store
    await store.clear_tenant(TEST_TENANT)



@pytest.mark.asyncio
async def test_i1_privacy_threshold(activity_store):
    """I1: Privacy threshold – signals protected below threshold."""
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
        
        for i in range(case["actors"]):
            event = ActivityEvent(
                event_id=f"{doc_id}-view-{i}",
                actor_principal_id=f"user-{i}",
                object_id=doc_id,
                event_type="view",
                source_system="test",
                event_time=datetime.now(timezone.utc),
            )
            await activity_store.ingest_event(TEST_TENANT, event)
        
        signals = await activity_store.get_document_signals(TEST_TENANT, doc_id)
        
        print(f"Actors: {case['actors']}, Protected: {signals.privacy_protected}, Expected: {case['protected']}")
        
        if case["protected"]:
            if signals.privacy_protected and signals.total_views is None:
                passed += 1
        else:
            if not signals.privacy_protected and signals.total_views == case["actors"]:
                passed += 1
    
    assert passed == len(test_cases)
    print("✅ I1: Privacy threshold correctly enforced")


@pytest.mark.asyncio
async def test_i2_retention_enforcement(activity_store):
    """I2: Retention enforcement – expired events purged."""
    print("\n[SIGNOFF I2] Retention Enforcement Test")
    print("=" * 60)
    
    from app.models.activity import ActivityEvent
    
    now = datetime.now(timezone.utc)
    
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
            ttl_seconds=1,
        )
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
            ttl_seconds=3600,
        )
        await activity_store.ingest_event(TEST_TENANT, event)
        active_events.append(event.event_id)
    
    print(f"Created {len(expired_events)} expired, {len(active_events)} active events")
    
    result = await activity_store.purge_expired(now=now)
    print(f"Purged: {result.purged_events}")
    
    # Verify expired gone, active remain
    for event_id in expired_events:
        stored = await activity_store.get_event(TEST_TENANT, event_id)
        assert stored is None
    
    for event_id in active_events:
        stored = await activity_store.get_event(TEST_TENANT, event_id)
        assert stored is not None
    
    print("✅ I2: Retention correctly enforced")


@pytest.mark.asyncio
async def test_i3_signal_freshness(activity_store):
    """I3: Signal freshness p95 ≤15 minutes."""
    print("\n[SIGNOFF I3] Signal Freshness Test")
    print("=" * 60)
    
    from app.models.activity import ActivityEvent
    
    n_probes = 20
    latencies = []
    
    for i in range(n_probes):
        user_id = f"probe-user-{i}"
        doc_id = f"probe-doc-{i}"
        
        event = ActivityEvent(
            event_id=f"probe-event-{i}",
            actor_principal_id=user_id,
            object_id=doc_id,
            event_type="view",
            source_system="test",
            event_time=datetime.now(timezone.utc),
        )
        
        start = time.perf_counter()
        await activity_store.ingest_event(TEST_TENANT, event)
        await activity_store.get_user_signals(TEST_TENANT, user_id)
        latencies.append(time.perf_counter() - start)
    
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    
    assert p95 <= 900  # 15 minutes in seconds
    print(f"✅ I3: p95 = {p95:.2f}s <= 900s")