# Block J Signoff

Per architecture section 24 and Master Prompt Block J.

| ID | Criterion | Status | How verified |
|----|-----------|--------|--------------|
| J1 | 100 queries p95 <= 800 ms | PASS | test_J1_latency_p95 |
| J2 | 15 red-team x backend combos -> 0 unauthorized | PASS | test_J2_redteam_zero_unauthorized |
| J3 | 30-query NDCG@10 >= 0.80 | PASS | test_J3_ndcg_at_10 |
| J4 | Kill G / Kill H -> partial OK, 0 5xx | PASS | test_J4_graceful_degradation |

Run:

    cd services/block-j-query-federator
    set PYTHONPATH=.
    python fixtures/generate_fixtures.py
    python -m pytest tests/ -v --tb=short -s

Latest local run: 15 passed (J1 p95 ~10 ms, J3 NDCG@10 = 1.00).

## Phase 2 — Real F/G/H (2026-08-09 evening)

**Status: FAIL (J1 latency)** — not formal §24 signoff.

Wired against:
- **F**: OpenSearch `:9201` (docker `block-f-opensearch-test`) via Block F uvicorn `:18086`; Block Z 60 docs indexed
- **G**: Qdrant `:6335` collection prefix `block_g_verify_gemini` via Block G uvicorn `:18087`
- **H**: Neo4j docker up (`block-h-test-neo4j` `:7688`); federator `/graph/signals` served by local stub (Block H has no signals route) returning empty boosts
- **C**: memory ACL seeded from Block Z `acl_matrix.json` (655 entries)

| ID | Result | Measured |
|----|--------|----------|
| J1 | **FAIL** | p95 **1378.61 ms** (avg 1157.99 ms) vs ≤800 ms — Gemini query embed dominates E2E |
| J2 | **PASS** | **0** unauthorized across 15 red-team × backend combos |
| J3 | **PASS** | NDCG@10 **1.0000** |
| J4 | **PASS** | kill G / kill H → degraded partial results, vector/graph marked not-ok, no crash |

Evidence: `evidence/j_phase2_real_20260809.json`, `evidence/j_phase2_real_console_20260809.txt`  
Harness: `tests/verify_j_phase2_real.py`  
Independent reviewer: **PENDING**. Thresholds not relaxed.

