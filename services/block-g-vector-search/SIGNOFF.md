# Block G: Vector Search Service — Signoff Document

Per architecture §24 (Block G signoff table) and Master Prompt Block G.

## Signoff Summary

| ID | Criterion | Phase 1 (Mock) | Phase 2 (Qdrant) | Date | Engineer | Reviewer | Fixtures | Environment |
|----|-----------|----------------|------------------|------|----------|----------|----------|-------------|
| G1 | Recall@10 ≥ 0.85 | **PASS** (1.0000) | **PASS** (1.0000) | 2026-08-05 | Cursor Agent | PENDING | block-g-local (Block Z schema) | Windows + snyq_qdrant:6333 |
| G2 | ACL prefilter zero leak | **PASS** (0 leaks / 15) | **PASS** (0 leaks / 15) | 2026-08-05 | Cursor Agent | PENDING | acl_redteam_cases.json | same |
| G3 | Latency p95 ≤ 150 ms | **PASS** (p95=0.63 ms) | **PASS** (p95=43.30 ms) | 2026-08-05 | Cursor Agent | PENDING | 100 queries | same |
| G4 | Model-version handling | **PASS** | **PASS** | 2026-08-05 | Cursor Agent | PENDING | dual v1/v2 upserts | same |

**Block signoff:** PASS pending independent reviewer signature (all G1–G4 green in Phase 1 and Phase 2).

---

## Detailed Evidence

### G1 — Recall@10

**Method:** 30 labeled queries from `fixtures/relevance_labels.json`; `top_k=10`; average recall vs `relevant_chunk_ids`.

**Phase 1 (MockVectorStore):**
```
VECTOR_DB_TYPE=mock pytest tests/test_recall.py -v -s
G1 Recall@10 average: 1.0000 (threshold 0.85)
PASSED
```

**Phase 2 (Qdrant @ localhost:6333):**
```
VECTOR_DB_TYPE=qdrant QDRANT_HOST=localhost QDRANT_PORT=6333 pytest tests/test_recall.py -v -s
G1 Recall@10 average: 1.0000 (threshold 0.85)
PASSED
```

---

### G2 — ACL Prefilter (Zero Leak)

**Method:** 15 red-team cases from `fixtures/acl_redteam_cases.json`. Query vectors aimed at restricted chunks; caller ACL = `group:eng` / `user:bob` (no legal/exec). Assert intersection with `forbidden_chunk_ids` is empty.

**Phase 1:** 0 restricted chunks leaked across 15 cases — PASS  
**Phase 2:** all 15 cases `leaked=[]` with `returned=50` (open-corpus hits only) — PASS

---

### G3 — Query Latency p95

**Method:** 100 searches mixing query embeddings and `top_k` ∈ {10,25,50,100}.

| Phase | Backend | avg | p95 | Threshold |
|-------|---------|-----|-----|-----------|
| 1 | MockVectorStore | 0.56 ms | 0.63 ms | ≤ 150 ms |
| 2 | Qdrant (snyq_qdrant) | 28.11 ms | 43.30 ms | ≤ 150 ms |

Both PASS.

---

### G4 — Model-Version Handling

**Method:** Upsert public chunks under `text-embedding-3-large` and `text-embedding-3-large-v2`.

- Filter `model_version=v2` → only v2 tagged results  
- Filter `model_version=v1` → only v1 tagged results  
- Unfiltered → both versions present; every result tagged; per-version scores monotonically ranked  

Phase 1 and Phase 2: PASS (no crashes).

---

## Fixture Provenance

Block Z shared fixture package is **not present** in this repository (same gap noted in Block E SIGNOFF).  
Block G ships local fixtures that match the master-prompt schema:

- `fixtures/relevance_labels.json` — 30 queries  
- `fixtures/acl_redteam_cases.json` — 15 red-team cases  
- `fixtures/corpus_chunks.json` — 90 chunks (30 public + 40 distractors + 20 restricted)  
- Regenerator: `fixtures/generate_fixtures.py`

Results are **provisional for fixture provenance** until Block Z publishes versioned shared fixtures; criteria G1–G4 themselves are met against this schema-compatible set.

---

## How to Re-run

```powershell
cd services/block-g-vector-search
$env:PYTHONPATH = (Get-Location).Path
$env:ENVIRONMENT = "test"

# Phase 1
$env:VECTOR_DB_TYPE = "mock"
python -m pytest tests/ -v --tb=short -s

# Phase 2 (requires Qdrant on 6333 — e.g. backend docker-compose snyq_qdrant)
$env:VECTOR_DB_TYPE = "qdrant"
$env:QDRANT_HOST = "localhost"
$env:QDRANT_PORT = "6333"
python -m pytest tests/ -v --tb=short -s
```

Optional isolated Qdrant: `docker compose -f docker-compose.test.yml up -d` then set `QDRANT_PORT=6335`.

---

## Deliverables Checklist

- [x] Source: `services/block-g-vector-search/app/`
- [x] Tests: G1–G4 in `tests/`
- [x] Fixtures (Block Z schema)
- [x] Docker: `Dockerfile`, `docker-compose.dev.yml`, `docker-compose.test.yml`
- [x] Integration guide for Block J: `INTEGRATION_GUIDE.md`
- [ ] Independent reviewer sign-off (below)

---

## Reviewer Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Engineer | Cursor Agent | 2026-08-05 | Implemented + verified G1–G4 Phase 1/2 |
| Independent Reviewer | _PENDING_ | | |

**Reviewer notes:** Confirm fixture swap to official Block Z package when available; wire Block A JWT signature verification before production.
---

## API path alignment (Master Prompt refresh 2026-08-05)

Routes mounted under `/api/v1` per Build & Signoff master prompt:

- `POST /api/v1/search/vector`
- `POST /api/v1/ingest`
- `GET /health`

Search request field `acl_terms` is canonical (`acl_filter_terms` accepted as alias).
Malformed requests return **400**; tenant binding failures return **403**.
