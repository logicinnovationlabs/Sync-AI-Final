"""Integration / signoff tests J1-J4 for Block J Query Federator."""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Set

import pytest

from app.models import SearchRequest, UserContext
from mocks.backend_server import corpus as mock_corpus
from tests.conftest import make_bearer


def _ndcg_at_k(ranked_ids: List[str], grades: Dict[str, float], k: int = 10) -> float:
    """Compute NDCG@k with graded relevance (missing grade = 0)."""
    dcg = 0.0
    for i, doc_id in enumerate(ranked_ids[:k]):
        rel = float(grades.get(doc_id, 0.0))
        if rel <= 0:
            continue
        dcg += (2**rel - 1) / math.log2(i + 2)

    ideal_rels = sorted((float(v) for v in grades.values() if v > 0), reverse=True)[:k]
    idcg = 0.0
    for i, rel in enumerate(ideal_rels):
        idcg += (2**rel - 1) / math.log2(i + 2)
    if idcg == 0:
        return 0.0
    return dcg / idcg


def _user_from_case(case: Dict[str, Any]) -> UserContext:
    return UserContext(
        tenant_id=case["tenant_id"],
        principal_id=case.get("principal_id") or case.get("user_id"),
        groups=case.get("groups") or [],
        acl_terms=case.get("acl_filter_terms") or [],
    )


@pytest.mark.asyncio
async def test_J1_latency_p95(federator_stack, representative_queries):
    """J1 Signoff: 100 representative federated queries -> p95 latency <= 800 ms."""
    federator, _store, _http = federator_stack
    queries = representative_queries["queries"]
    assert len(queries) == 100, "J1 requires 100 representative queries"

    latencies: List[float] = []
    for q in queries:
        user = UserContext(
            tenant_id=q["tenant_id"],
            principal_id=q.get("principal_id") or q.get("user_id"),
            groups=q.get("groups") or ["group:eng"],
            acl_terms=q.get("acl_filter_terms") or [],
        )
        req = SearchRequest(query=q["query"], size=10)
        started = time.perf_counter()
        resp = await federator.search(req, user)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        latencies.append(elapsed_ms)
        assert resp.total >= 0
        assert all(r.document_id for r in resp.results)

    ordered = sorted(latencies)
    idx = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    p95 = ordered[idx]
    print(f"\nJ1 p95 latency: {p95:.2f} ms (threshold 800 ms); max={ordered[-1]:.2f}")
    assert p95 <= 800.0, f"J1 FAIL: p95={p95:.2f} ms > 800 ms"


@pytest.mark.asyncio
async def test_J2_redteam_zero_unauthorized(federator_stack, redteam):
    """J2 Signoff: 15 red-team cases x backend combinations -> 0 unauthorized results."""
    federator, _store, _http = federator_stack
    cases = redteam["cases"]
    assert len(cases) == 15, "Block Z ACL red-team set must contain 15 cases"

    leaks = []
    for case in cases:
        combinations = case.get("backend_combinations") or [["lexical", "vector", "graph"]]
        forbidden: Set[str] = set(case.get("forbidden_document_ids") or [])
        user = _user_from_case(case)
        req = SearchRequest(query=case["query"], size=50)

        for combo in combinations:
            mock_corpus.kill_lexical = "lexical" not in combo
            mock_corpus.kill_vector = "vector" not in combo
            mock_corpus.kill_graph = "graph" not in combo
            if mock_corpus.kill_lexical and mock_corpus.kill_vector:
                continue

            resp = await federator.search(req, user)
            returned = {r.document_id for r in resp.results}
            leaked = sorted(returned & forbidden)
            if leaked:
                leaks.append({"case_id": case["case_id"], "combo": combo, "leaked": leaked})

    mock_corpus.kill_lexical = False
    mock_corpus.kill_vector = False
    mock_corpus.kill_graph = False

    assert not leaks, f"J2 FAIL: unauthorized results: {leaks}"
    print("\nJ2 ACL enforcement: 0 unauthorized across 15 cases x backend combos")


@pytest.mark.asyncio
async def test_J3_ndcg_at_10(federator_stack, relevance):
    """J3 Signoff: 30-query labeled relevance set -> NDCG@10 >= 0.80."""
    federator, _store, _http = federator_stack
    queries = relevance["queries"]
    assert len(queries) == 30, "Block Z relevance set must contain 30 queries"

    scores = []
    for q in queries:
        user = UserContext(
            tenant_id=q["tenant_id"],
            principal_id=q["principal_id"],
            groups=q.get("groups") or [],
            acl_terms=q.get("acl_filter_terms") or [],
        )
        req = SearchRequest(
            query=q["query_text"],
            size=10,
            query_embedding=q.get("query_embedding"),
        )
        resp = await federator.search(req, user)
        ranked_ids = [r.document_id for r in resp.results]
        grades = {
            doc_id: float(g)
            for doc_id, g in (q.get("relevance_grades") or {}).items()
        }
        for doc_id in q.get("relevant_document_ids") or []:
            grades.setdefault(doc_id, 3.0)
        ndcg = _ndcg_at_k(ranked_ids, grades, k=10)
        scores.append(ndcg)
        print(
            f"  {q['query_id']}: NDCG@10={ndcg:.3f} "
            f"top={ranked_ids[:3]} relevant={q.get('relevant_document_ids')}"
        )

    avg = sum(scores) / len(scores)
    print(f"\nJ3 NDCG@10 average: {avg:.4f} (threshold 0.80)")
    assert avg >= 0.80, f"J3 FAIL: NDCG@10={avg:.4f} < 0.80"


@pytest.mark.asyncio
async def test_J4_graceful_degradation(federator_stack, representative_queries):
    """J4 Signoff: kill G then H; valid partial results with 0 5xx errors."""
    federator, _store, _http = federator_stack
    sample = representative_queries["queries"][:20]

    async def _run_batch():
        errors = []
        for q in sample:
            user = UserContext(
                tenant_id=q["tenant_id"],
                principal_id=q.get("principal_id") or q.get("user_id"),
                groups=q.get("groups") or ["group:eng"],
                acl_terms=q.get("acl_filter_terms") or [],
            )
            req = SearchRequest(query=q["query"], size=10)
            try:
                resp = await federator.search(req, user)
            except Exception as exc:
                errors.append((q["query_id"], str(exc)))
                continue
            assert isinstance(resp.results, list)
            assert resp.took_ms >= 0
        return errors

    mock_corpus.kill_vector = True
    mock_corpus.kill_graph = False
    mock_corpus.kill_lexical = False
    errs_g = await _run_batch()
    assert not errs_g, f"J4 FAIL after killing G: {errs_g}"

    mock_corpus.kill_vector = False
    mock_corpus.kill_graph = True
    errs_h = await _run_batch()
    assert not errs_h, f"J4 FAIL after killing H: {errs_h}"

    mock_corpus.kill_vector = False
    mock_corpus.kill_graph = False
    print("\nJ4 graceful degradation: 0 5xx with G killed and with H killed")


@pytest.mark.asyncio
async def test_api_search_endpoint(api_client):
    """Smoke test for POST /api/v1/search through the FastAPI app."""
    client, _mock = api_client
    token = make_bearer("tenant_j_test", "user:alice", groups=["group:eng"])
    resp = await client.post(
        "/api/v1/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "How does kubernetes work?", "size": 5},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "results" in body
    assert body["took_ms"] >= 0
    ids = [r["document_id"] for r in body["results"]]
    assert "doc-public-00" in ids


@pytest.mark.asyncio
async def test_all_backends_down_returns_error(federator_stack):
    federator, _store, _http = federator_stack
    mock_corpus.kill_lexical = True
    mock_corpus.kill_vector = True
    mock_corpus.kill_graph = True
    user = UserContext(
        tenant_id="tenant_j_test",
        principal_id="user:alice",
        groups=["group:eng"],
        acl_terms=["group:eng", "user:alice"],
    )
    with pytest.raises(RuntimeError, match="All retrieval backends failed"):
        await federator.search(SearchRequest(query="kubernetes"), user)
    mock_corpus.kill_lexical = False
    mock_corpus.kill_vector = False
    mock_corpus.kill_graph = False
