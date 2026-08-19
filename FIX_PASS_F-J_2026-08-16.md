# Fix Pass — Block F Phase 2 (real OpenSearch), then Block J Phase 2

**Repo:** `logicinnovationlabs/Sync-AI-Final`  
**Branch:** `Pratham`  
**Commit tested:** `5ce77b1 Add: Block N completed and tested`  
**Date:** 2026-08-16  
**Mode:** Verify-and-fix. No commit, no push, `SIGNOFF.md` not touched.

`.bak` was taken before every existing file edit (`*.bak` is gitignored).

---

## 4.1 Block F — Phase 2, real OpenSearch

### What was brought up

From `services/block-f-lexical-search`:

```
docker compose -f docker-compose.test.yml up -d
```

Container: `block-f-opensearch-test` (`opensearchproject/opensearch:2.17.1`), host port **9201** → container 9200. Security plugin disabled (`DISABLE_SECURITY_PLUGIN=true`); no username/password env vars on this service.

**Ready check** (not just “container started”):

```
GET http://localhost:9201/_cluster/health
status=200
{"cluster_name":"docker-cluster","status":"green",...,"active_shards_percent_as_number":100.0}
docker: block-f-opensearch-test Up … (healthy)
```

Phase 2 env (same pattern as G’s `VECTOR_DB_TYPE=qdrant`):

```
$env:SEARCH_BACKEND = "opensearch"
$env:OPENSEARCH_HOST = "localhost"
$env:OPENSEARCH_PORT = "9201"
$env:ENVIRONMENT = "test"
```

`opensearch-py` was not installed; `requirements.txt` pins `opensearch-py>=2.7.0`. Installed **3.2.0** (latest matching the pin). Client `index`/`search`/`indices.*` APIs used by `OpenSearchLexicalStore` worked against 2.17.1; no pin bump required.

### Per-criterion results (final re-run)

```
$env:SEARCH_BACKEND = "opensearch"
$env:OPENSEARCH_HOST = "localhost"
$env:OPENSEARCH_PORT = "9201"
python -m pytest tests/ -v --tb=short -s
```

```
============================= 11 passed in 52.07s =============================
```

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| F1 | query latency p95 ≤ 200ms | **PASS** | `n=100 avg=49.44ms p95=53.47ms` (wrapper); `avg=48.80ms p95=51.28ms` (`test_latency.py`) |
| F2 | ACL 0 unauthorized / 15 cases | **PASS** | `0 unauthorized across 15 cases` (both wrappers) |
| F3 | index lag p95 < 30s | **PASS** | `n=20 avg=0.1139s p95=0.1271s` (wrapper); `p95=0.1435s` (`test_index_lag.py`) |
| F4 | facet accuracy 100% | **PASS** | `F4 mismatches: none` / `100% match` |

### Failures found on the first real run, and what actually caused them

First real-infra run: **F1 PASS, F2 PASS, F3 FAIL, F4 FAIL**. Hypotheses in the prompt (credential names, client pin) did **not** match. Root causes:

**F3 — pattern tokenizer ate the probe token (not lag, not credentials)**

`test_F3_index_lag_p95` searches for `uniqueToken{i}`. `code_tokenizer` was a `pattern` tokenizer **without** `group`. OpenSearch default `group=-1` treats the pattern as a **delimiter**, so camelCase/alnum matches are discarded instead of emitted as tokens. The Python tokenizer in `app/services/tokenizer.py` keeps those pieces. Indexing used `refresh=True`; the doc was in the index but not searchable as `uniqueToken0`.

**Change:** `app/services/opensearch_store.py` — `"group": 1` on `code_tokenizer`. `.bak` taken. Existing test indexes are deleted/recreated per fixture (`clear_tenant`).

**Re-run:** `F3 index lag: n=20 avg=0.1171s p95=0.1348s (threshold 30s) PASSED`

**F4 — three real-cluster vs mock differences**

1. **Deny ACL not in the OpenSearch prefilter.** Mock `acl_allows()` drops docs with `deny:group:eng`. The OS filter was only `terms: {acl_filter_terms: user_terms}`, so deny-tagged docs still matched `group:eng` and inflated aggregations (`visible_total` 49 vs expected 47). F2 still passed because **hits** are post-filtered; **facets/total** were not.
2. **Empty `repository` keyword buckets.** Mock `compute_facets` skips `""`; OS `terms` agg does not.
3. **Duplicate tags counted twice in fixtures/mock.** `doc-public-15` has `tags: ["gmail", "public", "gmail"]`. Mock/ground truth counted `gmail` twice; OS `terms` agg is unique per document (5 vs 6).

**Changes:**

- `app/services/acl_filter.py` — `bool` filter with `must` overlap **and** `must_not` on `deny:<term>`. `.bak` taken.
- `app/services/opensearch_store.py` — `exclude: ""` on facet aggs; drop empty keys when mapping buckets. `.bak` taken (same file as F3).
- `app/services/facets.py` — unique tags per document (match OS). `.bak` taken.
- `fixtures/generate_fixtures.py` and `fixtures/facet_ground_truth.json` — `gmail` count 6 → 5. `.bak` taken.

**Re-run:** `F4 mismatches: none` / **PASS** (then full suite 11 passed).

F1 p95 ~50ms on a cold local cluster is well under 200ms; not treated as an environment artifact that needed a code chase.

---

## 4.2 Block J — Phase 2 (reached; F1–F4 all passed)

### Real services live during the run

| Service | Infra | HTTP app | Health |
|---------|-------|----------|--------|
| **F lexical** | OpenSearch `localhost:9201` green | uvicorn `127.0.0.1:8086` `SEARCH_BACKEND=opensearch` | `{"status":"healthy","search_backend":"opensearch"}` |
| **G vector** | Qdrant `localhost:6335` `200 all shards are ready` | uvicorn `127.0.0.1:8087` `VECTOR_DB_TYPE=qdrant` `QDRANT_PORT=6335` | `{"status":"healthy","vector_db_type":"qdrant"}` |
| **H graph** | Neo4j `block-h-test-neo4j` bolt `localhost:7688` healthy | uvicorn `127.0.0.1:8088` `GRAPH_BACKEND=neo4j` `NEO4J_URI=bolt://localhost:7688` | `{"status":"healthy","graph_backend":"neo4j","backend_detail":"neo4j-ok"}` |

G and H test compose containers from the prior session were still up; they were not assumed blindly — Qdrant `/readyz` and Neo4j container health were re-checked, then F/G/H HTTP processes were started fresh.

### Why env-var swap alone was not enough

J’s `federator_stack` fixture always wired F/G/H to the in-process ASGI **mock** (`mocks/backend_server.py`). Setting `LEXICAL_SEARCH_URL` / `VECTOR_SEARCH_URL` / `GRAPH_SERVICE_URL` did not change that. Running the suite without a harness change would have been a false Phase 2 pass.

**Change:** `services/block-j-query-federator/tests/conftest.py` (`.bak` taken). When `USE_REAL_SERVICES=1`:

- Seed J’s fixture corpus into live F (`POST /_internal/index`) and G (`POST /api/v1/ingest`) with the same mock hash embedder J uses at query time.
- Point the federator at `http://127.0.0.1:8086/8087/8088`.
- Keep J2/J4 `mock_corpus.kill_*` flags as **client-side** short-circuits so backend-combination / graceful-degradation tests still work against real HTTP.

H has no `POST /graph/signals` (Block J client already treats HTTP 404 as empty signals). Graph is therefore degraded-by-contract on the real H app; J4 still requires 0 uncaught 5xx when G or H is killed.

### Per-criterion results

```
$env:USE_REAL_SERVICES = "1"
$env:LEXICAL_SEARCH_URL = "http://127.0.0.1:8086"
$env:VECTOR_SEARCH_URL = "http://127.0.0.1:8087"
$env:GRAPH_SERVICE_URL = "http://127.0.0.1:8088"
python -m pytest tests/test_federator.py::test_J1_latency_p95 tests/test_federator.py::test_J2_redteam_zero_unauthorized tests/test_federator.py::test_J3_ndcg_at_10 tests/test_federator.py::test_J4_graceful_degradation -v --tb=short -s
```

```
======================== 4 passed in 81.73s (0:01:21) =========================
```

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| J1 | 100 queries p95 ≤ 800ms | **PASS** | `J1 p95 latency: 296.35 ms (threshold 800 ms); max=336.59` |
| J2 | 0 unauthorized × backend combos | **PASS** | `J2 ACL enforcement: 0 unauthorized across 15 cases x backend combos` |
| J3 | NDCG@10 ≥ 0.80 | **PASS** | `J3 NDCG@10 average: 1.0000 (threshold 0.80)` (all 30 queries 1.000) |
| J4 | kill G / kill H → 0 5xx | **PASS** | `J4 graceful degradation: 0 5xx with G killed and with H killed` |

No J criterion needed a second fix attempt after the real-harness wiring.

---

## 4.3 If J wasn’t reached

Not applicable. F1–F4 all passed on real OpenSearch; J Phase 2 was run.

---

## 4.4 Noticed but not fixed

- `opensearch-py>=2.7.0` resolved to **3.2.0** against OpenSearch **2.17.1**. It worked; a tighter `==2.x` pin was not required this session.
- Block H has no `/graph/signals` route; J’s client already 404-degrades. Real Phase 2 graph boosts are empty unless that route is added later.
- J `api_client` / `test_api_search_endpoint` still uses ASGI mocks even when `USE_REAL_SERVICES=1` (only `federator_stack` / J1–J4 were switched).
- F/G test-mode JWT stubs default to `tenant_f_test` / `tenant_g_test` when no bearer is sent; Phase 2 J clients now attach a tenant-matching bearer. Production still needs Block A tokens.
- Evidence files rewritten by the F suite (`evidence/lag_measurement.csv`, `facet_comparison.json`, `redteam_report.json`) — test outputs, not product code.
- Dirty files from earlier sessions, not edited here: Block D/E/G fix-pass diffs, Block I evidence JSON.
- `docker-compose.test.yml` still has an obsolete `version:` attribute (compose warning only).
- Independent reviewer signoff per architecture §24 rule 1 is still required for D–J; this report is not that signoff.

---

## 4.5 Overall D–J status

Phase 2 = real infra for that block’s store (not mock). Official signoff still needs an independent reviewer.

| Block | Phase 1 (mock) | Phase 2 (real infra) | Notes |
|-------|----------------|----------------------|--------|
| D Storage | PASS (prior) | **PASS** (local compose PG `:5435` + MinIO; last fix pass) | Hosted Supabase pgcrypto was not this path |
| E Chunking | PASS (prior) | **PASS** (local compose PG `:5433`; last fix pass) | E2 wrapper is 30s mock-embed harness, not 10-min |
| F Lexical | PASS (prior) | **PASS this session** (OpenSearch 2.17.1 `:9201`) | F3/F4 needed real-cluster mapping/ACL/facet fixes |
| G Vector | PASS (prior) | **PASS** (Qdrant 1.12.1 `:6335`; last fix pass) | `qdrant-client==1.12.1` |
| H Graph | PASS (prior) | **PASS** (Neo4j 5.26 `:7688`; prior verification) | Confirmed still healthy this session |
| I Signals | PASS (prior) | **PASS** (Postgres `:15433`; prior verification) | Not re-run this session |
| J Federator | PASS (prior) | **PASS this session** (real F + G + H HTTP) | `USE_REAL_SERVICES=1`; graph signals 404-degraded |

**Bottom line:** F and J are now Phase 2 green against real OpenSearch / Qdrant / Neo4j. Combined with the previous D/E/G fix pass and the earlier H/I verification, **D–J are all Phase 2 real-infra clean on this machine and commit**, pending independent §24 reviewer signoff.

Stopped here. No commit, no `SIGNOFF.md` edits, no Blocks K–O.
