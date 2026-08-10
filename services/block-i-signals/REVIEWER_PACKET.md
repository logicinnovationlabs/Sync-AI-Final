# Block I — Independent Reviewer Verification Packet (I1–I3)

> **§24.1:** Independent human reviewer required. **Not** a signoff. See `services/block-i-signals/SIGNOFF.md`.

| Field | Value |
|-------|-------|
| Block | I — Activity / Signals |
| Engineer self-report | I1–I3 **PASS** (Phase 1 + Phase 2 Postgres, 2026-08-08) |
| Reviewer | **PENDING** |
| `fixtures_version` | **v2.1** |

---

## Isolation — Docker Compose

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-i-signals"
docker compose -f docker-compose.test.yml up -d postgres
```

Postgres **:15433**, `postgresql://signals:signals@localhost:15433/block_i_signals`.

---

## Required Environment Variables

| Variable | Phase 1 | Phase 2 |
|----------|---------|---------|
| `SIGNALS_BACKEND` | `mock` | `postgres` |
| `DATABASE_URL` | — | `postgresql://signals:signals@localhost:15433/block_i_signals` |
| `PYTHONPATH` | service root | service root |

---

## Reproduce Criteria (from `SIGNOFF.md`)

### Phase 1

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-i-signals"
$env:PYTHONPATH = (Get-Location).Path
$env:ENVIRONMENT = "test"
$env:SIGNALS_BACKEND = "mock"
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\ -v --tb=short -s
```

### Phase 2

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-i-signals"
docker compose -f docker-compose.test.yml up -d postgres
$env:SIGNALS_BACKEND = "postgres"
$env:DATABASE_URL = "postgresql://signals:signals@localhost:15433/block_i_signals"
$env:PYTHONPATH = (Get-Location).Path
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\ -v --tb=short -s
```

| ID | Pass threshold |
|----|----------------|
| I1 | Privacy threshold 4/4 |
| I2 | Retention purge complete |
| I3 | Freshness p95 ≤900 s |

Evidence: `evidence/i1_privacy_report_phase2.json`, `evidence/i2_retention_report_phase2.json`, `evidence/i3_freshness_report_phase2.json`.

---

## Reviewer PASS/FAIL Table

| ID | Criterion | Engineer self-report | Reviewer PASS/FAIL | Evidence | Notes |
|----|-----------|---------------------|-------------------|----------|-------|
| I1 | Privacy threshold | PASS | | | |
| I2 | Retention enforcement | PASS | | | |
| I3 | Signal freshness p95 ≤15 m | PASS | | | |

**Reviewer name / date / signature:** _______________
