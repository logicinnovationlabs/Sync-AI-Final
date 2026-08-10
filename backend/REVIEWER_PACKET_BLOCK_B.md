# Block B — Independent Reviewer Verification Packet (B1–B5)

> **§24.1:** Independent human reviewer required. **Not** a signoff. See `backend/SIGNOFF_BLOCK_B.md`.

| Field | Value |
|-------|-------|
| Block | B — Google Connector + Celery Ingestion |
| Engineer self-report | **PARTIAL** — Master B5 Phase 1 mock PASS + Phase 2 real Gmail PASS (2026-08-09); full B1–B7 Drive+Gmail re-validation still required |
| Reviewer | **PENDING** |
| `fixtures_version` | **v2** |

**Status:** `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REFRESH_TOKEN` wired via `seed_token_store_from_env()` → TokenStore key `google_oauth:{tenant_id}`. Testing-app refresh token expires ~**2026-08-16** (renew via same OAuth client).

---

## Isolation — Docker Compose

```powershell
cd "D:\PROJECTS\Sync Ai Final\backend"
docker compose -f docker-compose.yml up -d redis qdrant celery-worker celery-beat
```

---

## Required Environment Variables

| Variable | Placeholder |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | `<GOOGLE_CLIENT_ID>` |
| `GOOGLE_CLIENT_SECRET` | `<GOOGLE_CLIENT_SECRET>` |
| `GOOGLE_REFRESH_TOKEN` | `<GOOGLE_REFRESH_TOKEN>` (do not print; Testing-app ~7-day expiry) |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8000/api/v1/connectors/google/callback` |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` |
| `EMBEDDING_PROVIDER` | `fake` (for B5 crawl path) |

Load from `backend/.env` into `$env:` without printing values.

---

## Reproduce Criteria (from `backend/SIGNOFF_BLOCK_B.md`)

### Master B5 — checkpoint resume (Phase 1 mock)

```powershell
cd "D:\PROJECTS\Sync Ai Final\backend"
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_signoff_block_b.py::test_b5_checkpoint_resume -v -s
```

### Master B5 — Phase 2 real Gmail

```powershell
cd "D:\PROJECTS\Sync Ai Final\backend"
# load GOOGLE_* into $env: without printing
$env:EMBEDDING_PROVIDER = "fake"
$env:B5_REAL_PAGE_SIZE = "2"
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_b5_checkpoint_resume_real.py -v -s
```

Expected (2026-08-09 measured): baseline 29 pages / 56 objects; kill after 14/29; resume final 56; 0 dupes/missing.  
Evidence: `backend/evidence/b5_real_gmail_checkpoint_20260809.txt`, `backend/evidence/b5_smoke_google_20260809.txt`.

### Contract-mock smoke

```powershell
cd "D:\PROJECTS\Sync Ai Final"
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_block_b.py::TestBlockB::test_b5_checkpoint_resume -v
```

---

## Reviewer PASS/FAIL Table

| ID | Criterion | Engineer self-report | Reviewer PASS/FAIL | Evidence | Notes |
|----|-----------|---------------------|-------------------|----------|-------|
| B1 | Backfill completeness | Not re-validated | | | |
| B2 | Webhook incremental correctness | Not re-validated | | | |
| B3 | Webhook authenticity rejection | Not re-validated | | | |
| B4 | Rate-limit resilience | Not re-validated | | | |
| B5 | Checkpoint resume | Phase 1 PASS; Phase 2 real Gmail PASS (2026-08-09) | | | Token renew ~2026-08-16 |

**Reviewer name / date / signature:** _______________
