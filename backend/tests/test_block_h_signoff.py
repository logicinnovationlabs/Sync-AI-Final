"""
Block H Signoff Tests: Knowledge Graph Service

Tests H1-H3 per signoff requirements:
- H1: Edge fidelity 100%
- H2: Traversal p95 <= 100 ms
- H3: Merge/split integrity (0 orphans)
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Test configuration
TEST_TENANT = "block-h-test"
FIXTURES_DIR = Path(__file__).parent.parent.parent / "services" / "block-h-graph" / "fixtures"


@pytest.fixture
async def graph_store():
    """Get graph store for testing - real or mock based on configuration."""
    from app.services.graph import get_graph_store
    from app.core.config import settings
    
    store = get_graph_store()
    
    # Log which backend we're using
    if settings.graph_backend == "neo4j":
        print(f"\n[REAL BACKEND] Using Neo4j at {settings.neo4j_uri}")
    else:
        print("\n[MOCK BACKEND] Using MockGraphStore")
    
    await store.ensure_tenant(TEST_TENANT)
    yield store
    await store.clear_tenant(TEST_TENANT)


@pytest.fixture
async def load_fixtures(graph_store):
    """Load test fixtures into graph store."""
    # Load graph edges from fixtures
    edges_file = FIXTURES_DIR / "graph_edges.json"
    if not edges_file.exists():
        pytest.skip(f"Fixtures not found: {edges_file}")
    
    try:
        with open(edges_file) as f:
            data = json.load(f)
    except Exception as e:
        pytest.skip(f"Could not load fixtures: {e}")
    
    edges = data.get("edges", [])
    for edge in edges:
        # Handle different fixture formats gracefully
        rel_type = edge.get("type") or edge.get("rel_type") or edge.get("relationship_type", "RELATED")
        await graph_store.upsert_edge(
            tenant_id=TEST_TENANT,
            rel_type=rel_type,
            source_id=edge.get("source_id", "unknown"),
            target_id=edge.get("target_id", "unknown"),
            properties=edge.get("properties", {}),
            source_label=edge.get("source_label"),
            target_label=edge.get("target_label"),
        )
    
    return {"edges": edges, "expected_counts": data.get("expected_counts", {})}


@pytest.mark.asyncio
async def test_h1_edge_fidelity(graph_store, load_fixtures):
    """
    H1: Edge Fidelity 100%
    
    Verify all edges from fixtures are correctly stored and retrievable.
    Expected: 183/183 edges match expected counts by type.
    """
    print("\n[SIGNOFF H1] Edge Fidelity Test")
    print("=" * 60)
    
    fixtures = load_fixtures
    expected = fixtures["expected_counts"]
    
    # Count edges by type
    actual = await graph_store.count_edges_by_type(TEST_TENANT)
    
    print(f"\nExpected edge counts: {expected}")
    print(f"Actual edge counts: {actual}")
    
    # Verify counts match
    total_expected = sum(expected.values())
    total_actual = sum(actual.values())
    
    print(f"\nTotal edges - Expected: {total_expected}, Actual: {total_actual}")
    
    mismatches = []
    for rel_type, count in expected.items():
        actual_count = actual.get(rel_type, 0)
        if actual_count != count:
            mismatches.append(f"{rel_type}: expected {count}, got {actual_count}")
    
    if mismatches:
        print(f"\n[FAIL] Edge count mismatches:")
        for m in mismatches:
            print(f"  - {m}")
        assert False, f"Edge fidelity check failed: {len(mismatches)} mismatches"
    
    print(f"\n[PASS] H1: All {total_actual}/{total_expected} edges verified")
    assert total_actual == total_expected


@pytest.mark.asyncio
async def test_h2_traversal_latency(graph_store, load_fixtures):
    """
    H2: Traversal p95 <= 100 ms
    
    Measure traversal latency for 50 depth-2 queries.
    Expected: p95 <= 100ms for mock store.
    """
    print("\n[SIGNOFF H2] Traversal Latency Test")
    print("=" * 60)
    
    fixtures = load_fixtures
    
    # Get list of node IDs for sampling
    node_ids = await graph_store.list_node_ids(TEST_TENANT)
    if len(node_ids) < 50:
        pytest.skip(f"Not enough nodes for latency test: {len(node_ids)} < 50")
    
    # Sample 50 start nodes
    import random
    random.seed(42)
    sample = random.sample(node_ids, min(50, len(node_ids)))
    
    latencies = []
    print(f"\nRunning {len(sample)} depth-2 traversals...")
    
    for i, node_id in enumerate(sample, 1):
        started = time.perf_counter()
        result = await graph_store.traverse(
            tenant_id=TEST_TENANT,
            start_node_id=node_id,
            relationship_types=None,
            depth=2,
            limit=100,
        )
        elapsed = time.perf_counter() - started
        latencies.append(elapsed * 1000)  # Convert to ms
        
        if i % 10 == 0:
            print(f"  Progress: {i}/{len(sample)}")
    
    # Calculate p95
    latencies.sort()
    p95_idx = min(len(latencies) - 1, int(len(latencies) * 0.95))
    p95 = latencies[p95_idx]
    avg = sum(latencies) / len(latencies)
    
    print(f"\nLatency stats:")
    print(f"  Samples: {len(latencies)}")
    print(f"  Average: {avg:.2f} ms")
    print(f"  p95: {p95:.2f} ms")
    print(f"  Threshold: 100 ms")
    
    if p95 <= 100:
        print(f"\n[PASS] H2: p95 = {p95:.2f} ms <= 100 ms")
    else:
        print(f"\n[FAIL] H2: p95 = {p95:.2f} ms > 100 ms")
        assert False, f"Traversal p95 {p95:.2f}ms exceeds 100ms threshold"
    
    assert p95 <= 100


@pytest.mark.asyncio
async def test_h3_merge_split_integrity(graph_store):
    """
    H3: Merge/Split Integrity
    
    Test person merge and snapshot-based split restore.
    Expected: 0 orphaned edges after split restore.
    """
    print("\n[SIGNOFF H3] Merge/Split Integrity Test")
    print("=" * 60)
    
    # Create two person nodes with edges
    await graph_store.upsert_node(
        TEST_TENANT, "Person", "person-alice",
        {"display_name": "Alice", "email": "alice@example.com"}
    )
    await graph_store.upsert_node(
        TEST_TENANT, "Person", "person-alice-gmail",
        {"display_name": "Alice", "email": "alice@gmail.com"}
    )
    await graph_store.upsert_node(
        TEST_TENANT, "Document", "doc-1",
        {"title": "Document 1"}
    )
    await graph_store.upsert_node(
        TEST_TENANT, "Document", "doc-2",
        {"title": "Document 2"}
    )
    
    # Create edges from both persons to documents
    await graph_store.upsert_edge(TEST_TENANT, "AUTHORED", "person-alice", "doc-1")
    await graph_store.upsert_edge(TEST_TENANT, "AUTHORED", "person-alice-gmail", "doc-2")
    await graph_store.upsert_edge(TEST_TENANT, "VIEWED", "person-alice", "doc-2")
    await graph_store.upsert_edge(TEST_TENANT, "VIEWED", "person-alice-gmail", "doc-1")
    
    print("\nBefore merge:")
    edges_before = await graph_store.get_edges_involving(TEST_TENANT, "person-alice-gmail")
    print(f"  Secondary (alice-gmail) has {len(edges_before)} edges")
    
    # Merge secondary into primary
    print("\nPerforming merge...")
    merge_result = await graph_store.merge_persons(
        TEST_TENANT, "person-alice", "person-alice-gmail"
    )
    
    print(f"  Edges redirected: {merge_result['edges_redirected']}")
    print(f"  Secondary deleted: {merge_result['secondary_deleted']}")
    
    # Verify secondary is gone
    edges_after_merge = await graph_store.get_edges_involving(TEST_TENANT, "person-alice-gmail")
    orphaned_after_merge = len(edges_after_merge)
    
    print(f"\nAfter merge:")
    print(f"  Secondary (alice-gmail) has {orphaned_after_merge} edges (should be 0)")
    
    # Split (restore)
    print("\nPerforming split (restore)...")
    split_result = await graph_store.split_persons(
        TEST_TENANT, "person-alice", "person-alice-gmail",
        snapshot=merge_result.get("snapshot")
    )
    
    print(f"  Restored: {split_result['restored']}")
    print(f"  Edges restored: {split_result['edges_restored']}")
    
    # Verify secondary edges are restored
    edges_after_split = await graph_store.get_edges_involving(TEST_TENANT, "person-alice-gmail")
    print(f"\nAfter split:")
    print(f"  Secondary (alice-gmail) has {len(edges_after_split)} edges (should be {len(edges_before)})")
    
    orphaned = abs(len(edges_after_split) - len(edges_before))
    
    if orphaned == 0:
        print(f"\n[PASS] H3: 0 orphaned edges after split")
    else:
        print(f"\n[FAIL] H3: {orphaned} orphaned edges found")
        assert False, f"Split integrity failed: {orphaned} orphaned edges"
    
    assert orphaned == 0


if __name__ == "__main__":
    print("\nBlock H Signoff Tests")
    print("=" * 60)
    print("Run with: pytest backend/tests/test_block_h_signoff.py -v -s")
