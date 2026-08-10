# Block F — Independent Reviewer Verification Packet (F1–F4)

> **§24.1:** Independent human reviewer required. **Not** a signoff. See `services/block-f-lexical-search/SIGNOFF.md`.

| Field | Value |
|-------|-------|
| Block | F — Lexical Search |
| Engineer self-report | F1–F4 **PASS** (Phase 1 + Phase 2 OpenSearch) |
| Reviewer | **PENDING** |
| `fixtures_version` | **v2.1** |

---

## Isolation — Docker Compose

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-f-lexical-search"
docker compose -f docker-compose.test.yml up -d
```

OpenSearch on **:9201** (`block-f-opensearch-test`).

---

## Required Environment Variables

| Variable | Phase 1 | Phase 2 |
|----------|---------|---------|
| `SEARCH_BACKEND` | `mock` | `opensearch` |
| `OPENSEARCH_HOST` | — | `localhost` |
| `OPENSEARCH_PORT` | — | `9201` |
| `PYTHONPATH` | service root | service root |
| `ENVIRONMENT` | `test` | `test` |

---

## Reproduce Criteria (from `SIGNOFF.md`)

### Phase 1

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-f-lexical-search"
$env:PYTHONPATH = (Get-Location).Path
$env:ENVIRONMENT = "test"
$env:SEARCH_BACKEND = "mock"
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" fixtures\generate_fixtures.py
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\ -v --tb=short -s
```

Reference F1:

```powershell
$env:SEARCH_BACKEND = "mock"
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_latency.py -v -s
```

### Phase 2

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-f-lexical-search"
docker compose -f docker-compose.test.yml up -d
$env:SEARCH_BACKEND = "opensearch"
$env:OPENSEARCH_HOST = "localhost"
$env:OPENSEARCH_PORT = "9201"
$env:PYTHONPATH = (Get-Location).Path
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\ -v --tb=short -s
```

| ID | Pass threshold |
|----|----------------|
| F1 | p95 ≤200 ms |
| F2 | 0 ACL leaks / 15 red-team |
| F3 | Index lag p95 <30 s |
| F4 | Facet accuracy 100% |

---

## Reviewer PASS/FAIL Table

| ID | Criterion | Engineer self-report | Reviewer PASS/FAIL | Evidence | Notes |
|----|-----------|---------------------|-------------------|----------|-------|
| F1 | Query latency p95 ≤200 ms | PASS | | | |
| F2 | ACL enforcement | PASS | | | |
| F3 | Index lag p95 <30 s | PASS | | | |
| F4 | Facet accuracy 100% | PASS | | | |

**Reviewer name / date / signature:** _______________
