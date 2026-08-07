# Block I: Activity Ingestion and Signal Service - Signoff Document

Per Master Prompt Block I (I1-I3) and architecture two-phase signoff.

## Signoff Summary

| ID | Criterion | Phase 1 (Mock) | Phase 2 (Postgres) | Date | Engineer | Reviewer | Fixtures | Environment |
|----|-----------|----------------|--------------------|------|----------|----------|----------|-------------|
| I1 | Privacy threshold | **PASS** (4/4 cases) | **PASS** (4/4 cases) | 2026-08-08 | Cursor Agent | PENDING | block-i-local (Block Z schema) | Windows + Docker Postgres :15433 |
| I2 | Retention enforcement | **PASS** (8/8 purged) | **PASS** (8/8 purged) | 2026-08-08 | Cursor Agent | PENDING | short-TTL fixtures | same |
| I3 | Signal freshness p95 <= 15m | **PASS** (p95=0.006s) | **PASS** (p95=0.174s) | 2026-08-08 | Cursor Agent | PENDING | events.json + probe | same |

**Block signoff:** PASS pending independent reviewer signature (all I1-I3 green in Phase 1 and Phase 2).

---

## Phase 1 - Provisional Signoff (against mock store)

| Criterion | Result | Evidence |
|-----------|--------|----------|
| I1 - Privacy Threshold | PASS | evidence/i1_privacy_report.json |
| I2 - Retention Enforcement | PASS | evidence/i2_retention_report.json |
| I3 - Signal Freshness | PASS | evidence/i3_freshness_report.json |
| Extra - Idempotency | PASS | test output |
| Extra - Tenant Isolation | PASS | test output |
| Extra - Scope Checks | PASS | test output |

- **Date**: 2026-08-08
- **Backend**: SIGNALS_BACKEND=mock
- **Conclusion**: ALL PASS

---

## Phase 2 - Integration Signoff (against real PostgreSQL)

| Criterion | Result | Evidence |
|-----------|--------|----------|
| I1 - Privacy Threshold | **PASS** | evidence/i1_privacy_report_phase2.json |
| I2 - Retention Enforcement | **PASS** | evidence/i2_retention_report_phase2.json |
| I3 - Signal Freshness | **PASS** (p95=0.1741s) | evidence/i3_freshness_report_phase2.json |
| Extra - Idempotency | **PASS** | evidence/phase2_test_run.log |
| Extra - Tenant Isolation | **PASS** | evidence/phase2_test_run.log |
| Extra - Scope Checks | **PASS** | evidence/phase2_test_run.log |

- **Date**: 2026-08-08
- **Engineer**: Cursor Agent
- **Reviewer**: (to be assigned per signoff process)
- **Environment**: Docker Postgres 16 (block-i-postgres-test) on localhost:15433
- **Connection**: postgresql://signals:signals@localhost:15433/block_i_signals
- **Backend**: SIGNALS_BACKEND=postgres
- **Schema**: migrations/001_initial.sql (+ auto-ensure in PostgresActivityStore)
- **Fixtures version**: v1 (block-i-local; Block Z schema-compatible)
- **Test log**: evidence/phase2_test_run.log
- **Conclusion**: **ALL PASS - Block I is ready for integration.**

### Phase 2 Detailed Evidence

#### I1 - Privacy Threshold
Actor counts 1 and 3 return privacy_protected=true with null numerics and no actor ID leakage.
Actor counts 5 and 10 return numeric popularity_score, total_views, and distinct_viewers.

#### I2 - Retention Enforcement
Purged 8 expired events (TTL elapsed); 5 active events retained; zero TTL-expired rows remaining after purge.

#### I3 - Signal Freshness
n=20 probe ingests against Postgres; avg=0.1554s; p95=0.1741s; threshold=900s. **PASS**.

## Additional checks

- Idempotency: re-ingest same event_id returns already_processed_count=1; counts unchanged.
- Tenant isolation: same document_id in tenant B does not reveal tenant A aggregates.
- Scope enforcement: missing activity.ingest scope returns 403.

## Fixture Provenance

Block Z shared fixtures/activity package is not present in this repository (same gap as E/F/G/H).
Block I ships local fixtures matching the master-prompt schema:

- fixtures/events.json
- fixtures/privacy_test_cases.json
- fixtures/retention_test_cases.json
- fixtures/signal_ground_truth.json
- Regenerator: fixtures/generate_fixtures.py

FIXTURES_PATH env override is supported.

## How to Re-run

```powershell
cd services/block-i-signals
$env:PYTHONPATH = (Get-Location).Path
$env:ENVIRONMENT = "test"

# Phase 1
$env:SIGNALS_BACKEND = "mock"
python -m pytest tests/ -v --tb=short -s

# Phase 2
docker compose -f docker-compose.test.yml up -d postgres
$env:SIGNALS_BACKEND = "postgres"
$env:DATABASE_URL = "postgresql://signals:signals@localhost:15433/block_i_signals"
python -m pytest tests/ -v --tb=short -s
```

Service port: 8089. OpenAPI: /docs. Contracts: contracts/openapi.yaml, contracts/asyncapi.yaml.

## API Surface

| Method | Path | Scope |
|--------|------|-------|
| POST | /activity/ingest | activity.ingest |
| GET | /signals/user/{user_id} | signals.read |
| GET | /signals/document/{document_id} | signals.read |
| POST | /admin/retention/purge | activity.ingest or signals.admin |
| GET | /health | - |

## Reviewer Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Engineer | Cursor Agent | 2026-08-08 | Phase 1 + Phase 2 evidence |
| Reviewer | | | PENDING |

**Final Status**: **PASS** (Phase 1 + Phase 2)
**Block Ready for Integration**: **YES** (dependency-ready for Blocks H, J, L)
