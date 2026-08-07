# Block F: Lexical Search Service - Sign-off Record

## Block Information
- **Block ID**: F
- **Engineer**: Suhani / Cursor Agent
- **Reviewer**: PENDING
- **Date**: 2026-08-05
- **Fixtures Version**: block-f-local (Block Z shared package absent; schema matches master prompt)

---

## Phase 1: Provisional Signoff (Against Block Z Mocks)

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| F1 | Query Latency (p95 <= 200ms) | **PASS** (p95=2.82ms) | [evidence/test_output_f1.txt](evidence/test_output_f1.txt) |
| F2 | ACL Enforcement (0 violations) | **PASS** (0 leaks / 15) | [evidence/redteam_report.json](evidence/redteam_report.json) |
| F3 | Index Lag (p95 < 30s) | **PASS** (p95=0.003s) | [evidence/lag_measurement.csv](evidence/lag_measurement.csv) |
| F4 | Facet Accuracy (100% match) | **PASS** | [evidence/facet_comparison.json](evidence/facet_comparison.json) |

**Phase 1 Signoff**: **PASS**
**Date**: 2026-08-05

---

## Phase 2: Integration Signoff (Against Real OpenSearch)

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| F1 | Query Latency (p95 <= 200ms) | PENDING | - |
| F2 | ACL Enforcement (0 violations) | PENDING | - |
| F3 | Index Lag (p95 < 30s) | PENDING | - |
| F4 | Facet Accuracy (100% match) | PENDING | - |

**Phase 2 Signoff**: PENDING (run with SEARCH_BACKEND=opensearch after docker compose -f docker-compose.test.yml up -d)

---

## Detailed Evidence (Phase 1)

### F1 - Query Latency
```
SEARCH_BACKEND=mock pytest tests/test_latency.py -v -s
F1 latency: n=100 avg=2.55ms p95=2.82ms (threshold 200ms)
PASSED
```

### F2 - ACL Enforcement
15 red-team cases from fixtures/acl_redteam_cases.json covering cross-tenant, no-access, allow, group-change, container inheritance, deny override, unauthenticated, insufficient scope, deleted, unshared, restricted container, multi-group, removed group, and parent/child deny. All returned leaked=[]. Unauthenticated case returned total=0.

### F3 - Index Lag
20 ingest.canonical.v1 publishes via CanonicalConsumer; p95 searchable lag ~ 3ms on mock backend.

### F4 - Facet Accuracy
Facet fields object_type, source, repository, owner, language, tags matched ground truth 100% for eng+alice ACL view (47 visible docs).

---

## Fixture Provenance

Block Z shared fixture package is **not present** in this repository (same gap as Blocks E/G). Block F ships local fixtures matching the master-prompt schema:

- fixtures/corpus_docs.json - 60 documents
- fixtures/acl_redteam_cases.json - 15 red-team cases
- fixtures/representative_queries.json - 100 queries
- fixtures/facet_ground_truth.json - facet counts
- Regenerator: fixtures/generate_fixtures.py

Results are **provisional for fixture provenance** until Block Z publishes versioned shared fixtures; criteria F1-F4 themselves are met against this schema-compatible set.

---

## How to Re-run

```powershell
cd services/block-f-lexical-search
$env:PYTHONPATH = (Get-Location).Path
$env:ENVIRONMENT = "test"
$env:SEARCH_BACKEND = "mock"
python fixtures/generate_fixtures.py
python -m pytest tests/ -v --tb=short -s
```

Phase 2:
```powershell
docker compose -f docker-compose.test.yml up -d
$env:SEARCH_BACKEND = "opensearch"
$env:OPENSEARCH_HOST = "localhost"
$env:OPENSEARCH_PORT = "9201"
python -m pytest tests/ -v --tb=short -s
```

---

## Deliverables Checklist

- [x] Source: services/block-f-lexical-search/app/
- [x] Tests: F1-F4 in tests/
- [x] Fixtures (Block Z schema)
- [x] Docker: Dockerfile, docker-compose.dev.yml, docker-compose.test.yml
- [x] Integration guide for Block J: INTEGRATION_GUIDE.md
- [x] Index template with code_analyzer + acl_filter_terms
- [x] POST /search/lexical + POST /_internal/index
- [x] Canonical consumer for ingest.canonical.v1
- [ ] Independent reviewer sign-off (below)
- [ ] Phase 2 OpenSearch signoff

---

## Reviewer Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | Suhani / Cursor Agent | 2026-08-05 | Phase 1 complete |
| Reviewer | | | PENDING |

**Final Status**: **PROVISIONAL PASS** (Phase 1)
**Block Ready for Integration**: **YES** (mock path; set SEARCH_BACKEND=opensearch for production)