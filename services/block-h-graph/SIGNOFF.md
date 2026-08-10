# Block H: Knowledge Graph Service - Signoff Document

Per Master Prompt Block H (H1-H3) and architecture two-phase signoff.

## Signoff Summary

| ID | Criterion | Phase 1 (Mock) | Phase 2 (Neo4j) | Date | Engineer | Reviewer | Fixtures | Environment |
|----|-----------|----------------|-----------------|------|----------|----------|----------|-------------|
| H1 | Edge fidelity 100% | **PASS** (183/183) | **PASS** (183/183) | 2026-08-06 | Cursor Agent | PENDING | block-h-local (Block Z schema) | Windows + Neo4j CE 5.26 @7688 |
| H2 | Traversal p95 <= 100 ms | **PASS** (p95=0.10 ms) | **PASS** (p95=15.53 ms) | 2026-08-06 | Cursor Agent | PENDING | 50 depth-2 starts | same |
| H3 | Merge/split integrity | **PASS** (0 orphans) | **PASS** (0 orphans) | 2026-08-06 | Cursor Agent | PENDING | person-alice / person-alice-gmail | same |

**Block signoff:** PASS pending independent reviewer signature (all H1-H3 green in Phase 1 and Phase 2).

## Detailed Evidence

### H1 - Edge Fidelity

Method: Load fixtures/graph_edges.json; compare count_edges_by_type vs expected_counts.

- Phase 1 (MockGraphStore): 183/183 PASS
- Phase 2 (Neo4j Community bolt://localhost:7688): 183/183 PASS

### H2 - Traversal Latency p95

Method: 50 depth-2 traversals from distinct start nodes; nearest-rank p95.

| Phase | Backend | avg | p95 | Threshold |
|-------|---------|-----|-----|-----------|
| 1 | MockGraphStore | 0.06 ms | 0.10 ms | <= 100 ms |
| 2 | Neo4j 5.26 CE | 15.06 ms | 15.53 ms | <= 100 ms |

Both PASS.

### H3 - Merge/Split Integrity

Method: Merge person-alice <- person-alice-gmail. Assert zero edges on secondary after merge; restore via snapshot split.

- Phase 1: redirected=4, orphans=0, restored_edges=4 PASS
- Phase 2: redirected=4, orphans=0, restored_edges=4 PASS

## Fixture Provenance

Block Z shared fixture package is not present (same gap as E/F/G). Block H ships local fixtures matching the master-prompt schema.
FIXTURES_PATH env override is supported. Regenerator: fixtures/generate_fixtures.py.

## Isolation Notes

- Phase 1: separate in-memory graphs per tenant_id.
- Phase 2: prefers graph_tenant_{id}; Neo4j Community falls back to default neo4j DB with mandatory tenant_id filters.

## How to Re-run

```powershell
cd services/block-h-graph
$env:PYTHONPATH = (Get-Location).Path
$env:ENVIRONMENT = "test"

# Phase 1
$env:GRAPH_BACKEND = "mock"
python -m pytest tests/ -v --tb=short -s

# Phase 2
docker compose -f docker-compose.test.yml up -d
$env:GRAPH_BACKEND = "neo4j"
$env:NEO4J_URI = "bolt://localhost:7688"
$env:NEO4J_PASSWORD = "blockh-dev-password"
python -m pytest tests/ -v --tb=short -s
```

Service port: 8088. OpenAPI: /docs.

## API Surface (stable for Block J)

| Method | Path | Scope |
|--------|------|-------|
| POST | /graph/traverse and /api/v1/graph/traverse | graph.read |
| GET | /people/search | people.read |
| GET | /graph/related/{id} | graph.read |
| POST | /admin/persons/merge | graph.admin |
| POST | /admin/persons/split | graph.admin |
| GET | /health | - |

## Reviewer Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Engineer | Cursor Agent | 2026-08-06 | Implemented + Phase 1/2 evidence |
| Reviewer | | | PENDING |
