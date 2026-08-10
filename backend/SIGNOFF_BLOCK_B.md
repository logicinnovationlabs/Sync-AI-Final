# BLOCK B SIGNOFF REPORT

**Block:** B — Google Connector Package + Push/Celery Ingestion Runtime  
**Version:** 0.3.0 (checkpoint resume / master B5)  
**Date:** 2026-08-08  
**Engineer:** Auto (agent implementation)  
**Reviewer:** _______________ (PENDING — no reviewer signature)  
**Environment:** Local Phase 1 mock (Windows host, `.venv` Python 3.14)  

---

## Criterion ID Mapping (master vs local suite)

| Master architecture ID | Master meaning | Local suite ID / test | Local meaning |
|------------------------|----------------|----------------------|---------------|
| **B5** | Checkpoint resume (kill mid-crawl → restart → no dupes/missing) | `test_b5_checkpoint_resume` | Same as master B5 |
| *(n/a — local-only)* | — | **Local B5** `test_B5_credential_leakage` | Credential leakage (logs must not contain OAuth token) |

Local suite B1–B7 numbering is unchanged. Master architecture B5 maps to **checkpoint resume**, not credential leakage. Credential leakage remains local B5.

---

## Signoff Criteria Results

**Block signoff: PASS only if B1–B7 all PASS for both Drive and Gmail services.**  
**Overall production-ready: NOT claimed.** Reviewer still PENDING.

| ID | Criterion | Test Method | Pass Threshold | Drive Result | Gmail Result | Evidence | Notes |
|----|-----------|-------------|----------------|--------------|--------------|----------|-------|
| **B1** | Backfill completeness | Run `backfill_tenant_source` against fixture source with known count N | Ingested count = N; 0 loss vs. fixture count | ☐ PASS<br>☐ FAIL | ☐ PASS<br>☐ FAIL | Prior suite | Unchanged this change |
| **B2** | Webhook-triggered incremental correctness | POST valid fixture notification, assert task fetched only delta (not full re-scan) | Correct end state reached without re-fetching already-ingested items | ☐ PASS<br>☐ FAIL | ☐ PASS<br>☐ FAIL | Prior suite | Unchanged |
| **B3** | Webhook authenticity rejection | POST forged/missing-signature notification to each endpoint | 403 returned; Celery task's `.delay()` never called | ☐ PASS<br>☐ FAIL | ☐ PASS<br>☐ FAIL | Prior suite | Unchanged |
| **B4** | Rate-limit resilience | Inject simulated 429s at 20% rate during task API calls | Task retries via Celery and eventually succeeds; 0 unhandled exceptions | ☐ PASS<br>☐ FAIL | ☐ PASS<br>☐ FAIL | Prior suite | Unchanged |
| **Local B5** | Credential leakage | Grep logs for fixture OAuth token | 0 matches of token in logs | ☐ PASS<br>☐ FAIL | ☐ PASS<br>☐ FAIL | `test_B5_credential_leakage` | Kept under local B5 ID |
| **Master B5** | Checkpoint resume | Kill mid-crawl after ~50%; restart; compare to uninterrupted baseline | Same object set; 0 dupes; 0 missing; resume from persisted cursor | **PASS** (Phase 1 mock, 2026-08-08) | **PASS** (2026-08-09) real Gmail kill/resume — see below | See below | Implemented 2026-08-08 |
| **B6** | Metadata allowlist enforcement | Feed document with metadata outside `allowed_metadata_keys` through `bulk_index` | Only allowlisted keys appear in Qdrant payload | ☐ PASS<br>☐ FAIL | ☐ PASS<br>☐ FAIL | Prior suite | Unchanged |
| **B7** | Watch channel renewal | Seed watch record expiring within renewal window; run `renew_watch_channels` | Renewal call made before stored expiration | ☐ PASS<br>☐ FAIL | ☐ PASS<br>☐ FAIL | Prior suite | Unchanged |

---

## Master B5 — Checkpoint Resume Evidence

### Implementation

- `run_two_pass_sync` paginates delta pages and invokes `on_cursor_update(next_cursor)` after each successfully indexed page.
- `backfill_tenant_source` loads `cursor_store.get_cursor` at start (resume) and persists via `update_cursor` after each page.
- Cursors live in PostgreSQL `sync_cursors` (`CursorStore`).

### Phase 1 (mock) — PASS

**Command:**
```powershell
cd "D:\PROJECTS\Sync Ai Final\backend"
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests/test_signoff_block_b.py::test_b5_checkpoint_resume -v -s
```

**Result (2026-08-08):**
```
tests/test_signoff_block_b.py::test_b5_checkpoint_resume
[PASS] Master B5: kill after 2/4 pages (cursor='2'); resume completed;
final=16 matches baseline=16, 0 dupes/missing
PASSED
======================= 1 passed, 21 warnings in 0.07s ========================
```

**Scenario exercised:**
1. Uninterrupted crawl of 16 objects (4 pages × 4) → baseline ID set
2. Kill after 2 pages (50%); checkpoint cursor `'2'` persisted
3. Resume from cursor; remaining 8 objects ingested
4. Final set equals baseline (count 16, no duplicates, no missing)

Contract-mock smoke (root suite): `tests/test_block_b.py::TestBlockB::test_b5_checkpoint_resume` still covers `/connectors/checkpoint` against the Phase 1 mock server.

### Phase 2 (real Google source) — PASS (2026-08-09)

Earlier same-day attempts were **BLOCKED** (token absent, then `invalid_grant`). After wiring `GOOGLE_REFRESH_TOKEN` into TokenStore seed path and obtaining a valid Testing-app refresh token for `syncai740@gmail.com`, Phase 2 **PASSED** against real Gmail. Full measured evidence (counts, kill/resume cursors, token expiry ~2026-08-16): see **“B5 Phase 2 — Real Google source PASS (2026-08-09)”** at end of this file.

Drive alone had only 1 file (insufficient for multi-page kill); Gmail used for the kill/resume run.

---

## Overall Result

☐ **PASS** — All B1–B7 criteria passed for both Drive and Gmail  
☐ **FAIL** — One or more criteria failed  
☒ **PARTIAL** — Master B5 checkpoint resume: Phase 1 mock PASS + Phase 2 real Gmail PASS (2026-08-09); full B1–B7 Drive+Gmail re-validation and reviewer signoff still required. **Not production-ready.**

---

## Test Execution Summary

**Command Run (master B5):**
```powershell
cd backend
..\..\.venv\Scripts\python.exe -m pytest tests/test_signoff_block_b.py::test_b5_checkpoint_resume -v -s
```

**Full local suite (optional):**
```powershell
pytest tests/test_signoff_block_b.py -v
```

**Test Duration:** ~0.07s (master B5 alone)

---

## Architecture Validation

### ✓ Non-Negotiable Rules Compliance

- [x] **Rule 1**: All Google code lives under `app/connectors/google/`
- [x] **Rule 2**: One shared OAuth token per tenant per Google account
- [x] **Rule 3**: Registry discovers connectors recursively (supports packages with multiple services)
- [x] **Rule 4**: No steady-state polling loops (push-driven only)
- [x] **Rule 5**: Webhook receivers do no fetching themselves (only validate & enqueue)
- [x] **Rule 6**: Watch channels expire and are renewed before expiration
- [x] **Rule 7**: Metadata is allowlisted before indexing (via manifest)
- [x] **Rule 8**: No hardcoded credentials (all from env/Vault)
- [x] **Rule 9**: All signoff tests are binary PASS/FAIL with mocked APIs
- [x] **Architecture B5**: Mid-crawl checkpoint persist + resume (Phase 1 mock proven)

---

## Evidence Attachments

- [x] Master B5 pytest output (Phase 1 mock PASS above)
- [ ] Test output logs (`pytest -v` full B1–B7 suite)
- [ ] Celery task execution logs (eager mode verification)
- [ ] Qdrant collection inspection (metadata allowlist verification)
- [ ] Webhook validation logs (403 rejection proof)
- [ ] Watch renewal logs (timing verification)
- [ ] Credential grep results (local B5 verification)
- [ ] Phase 2 real-source checkpoint resume

---

## Key Metrics

| Metric | Drive | Gmail | Notes |
|--------|-------|-------|-------|
| **Backfill Documents** | _____ | _____ | From fixture count |
| **Checkpoint resume objects (mock)** | 16 | N/A | Master B5 Phase 1 |
| **Kill point** | 50% (2/4 pages) | N/A | cursor=`'2'` |
| **Incremental Fetch Latency** | _____ | _____ | Webhook → Index time |
| **Watch Renewal Count** | _____ | _____ | Number of renewals performed |
| **Metadata Keys Filtered** | _____ | _____ | Disallowed keys removed |
| **Rate Limit Retries** | _____ | _____ | 429 retry attempts |

---

## Component Verification

### OAuth Manager
- [ ] Tokens stored securely
- [ ] Automatic refresh working
- [ ] Shared across Drive & Gmail

### Connectors
- [ ] `DriveConnector` implements `BaseConnector`
- [ ] `GmailConnector` implements `BaseConnector`
- [ ] Both use shared OAuth manager
- [ ] Transform produces valid `UnifiedDocument`

### Webhooks
- [ ] Drive webhook validates channel token
- [ ] Gmail webhook validates Pub/Sub auth
- [ ] Both enqueue tasks and return < 1s
- [ ] Forged notifications rejected

### Celery Tasks
- [x] `backfill_tenant_source` loads resume cursor and persists per page
- [ ] `backfill_tenant_source` completes successfully (full Google fixture path)
- [ ] `process_drive_notification` fetches only delta
- [ ] `process_gmail_notification` fetches only delta
- [ ] `renew_watch_channels` renews before expiry
- [ ] All tasks support retry on 429

### Indexer & Storage
- [ ] Metadata allowlist enforced via manifest
- [ ] Embeddings generated (fake mode in tests)
- [ ] Qdrant upserts successful
- [ ] Deletions handled correctly
- [x] Cursor store persists mid-crawl resume points (per-page checkpoint)

---

## Reviewer Notes

Reviewer signature **PENDING**. Master B5 Phase 1 mock evidence recorded by implementing engineer/agent only.

---

## Known Limitations

1. **Test Mode**: Tests use `task_always_eager=True` for synchronous execution
2. **Fake Embeddings**: Tests use deterministic fake embeddings, not real Gemini
3. **Mock APIs**: No real Google API calls in master B5 test (paginated in-memory connector)
4. **Single Tenant**: Tests focus on single-tenant scenarios
5. **Re-backfill vs incremental cursor**: A completed crawl may leave an incremental/start page token in `sync_cursors`; a later full re-backfill would treat that as a files.list page token unless the cursor is cleared first
6. **Kill mid-page**: Checkpoint is after a full page index; a kill mid-page re-fetches that page on resume (upsert-safe, at-least-once)
7. **Phase 2**: Real Google source kill/resume not executed

---

## Production Readiness Checklist

- [ ] Google Cloud project created with Drive + Gmail APIs enabled
- [ ] OAuth credentials generated (Client ID + Secret)
- [ ] Pub/Sub topic created for Gmail push notifications
- [ ] Public webhook URL configured (ngrok or production domain)
- [ ] SSL/TLS certificates in place for webhook HTTPS
- [ ] Gemini API key configured for embeddings
- [ ] Qdrant collection initialized with correct dimension
- [ ] Celery worker + beat running in production
- [ ] Watch renewal monitoring in place
- [ ] Rate limit quotas reviewed and increased if needed
- [ ] Phase 2 real-source checkpoint resume validated
- [ ] Reviewer signoff obtained

---

## Sign-Off

**Engineer Signature:** Auto / implementation agent — Phase 1 master B5 evidence only  
**Reviewer Signature:** _______________ (PENDING)  
**Date:** 2026-08-08  

---

## Next Steps

- [ ] Re-run full `test_signoff_block_b.py` B1–B7 for Drive + Gmail
- [ ] Phase 2: real-source mid-crawl kill/resume
- [ ] Reviewer signoff
- [ ] Ready for Block C (Normalization) development only after full B gate
- [ ] Documentation updated with production deployment guide

---

**Status:** ☐ Provisional Signoff ☐ Integration Signoff ☐ Production Ready  
**This update:** Master B5 Phase 1 mock **PASS** only — **not** overall production-ready.

### B5 Phase 2 credential re-check (2026-08-09 session — Final Verification)

Presence-only check (values not printed):
- `GOOGLE_CLIENT_ID`: **present**
- `GOOGLE_CLIENT_SECRET`: **present**
- `GOOGLE_REDIRECT_URI`: `http://localhost:8000/api/v1/connectors/google/callback`
- `GOOGLE_REFRESH_TOKEN` / `GMAIL_REFRESH_TOKEN` / `DRIVE_REFRESH_TOKEN`: **absent**

`tests/test_signoff_block_b.py::test_b5_checkpoint_resume` has **no** `USE_REAL_SOURCE` flag — mock-only paginated connector.

**Status: BLOCKED** — cannot run real Drive/Gmail kill/resume without a consented user refresh token (or equivalent stored connector token). Not a FAIL of the mock B5 implementation; not a Phase 2 PASS.

**Needed to unblock:** OAuth consent → persist refresh token for Drive and/or Gmail; then add/run a real-source B5 variant against a multi-page folder.

### B5 Phase 2 attempt after GOOGLE_REFRESH_TOKEN added (2026-08-09)

**Credential presence:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` all present (values not printed).

**Test added:** `tests/test_b5_checkpoint_resume_real.py` — real DriveConnector + kill/resume via `run_two_pass_sync`, page_size=5.

**Attempts (max 2):**
1. Async `GoogleOAuthManager.get_valid_token` under pytest — failed with nest_asyncio/httpx `weakref` crash (infrastructure/test harness issue, not Google).
2. Sync `POST https://oauth2.googleapis.com/token` with `grant_type=refresh_token` — **HTTP 400 `invalid_grant` / Bad Request**.

**Status: BLOCKED (invalid credentials)** — not a mock re-run, not a PASS. Google rejected the refresh token for this OAuth client. Common causes: token from a different client ID, revoked consent, refresh token not issued with `access_type=offline` + `prompt=consent`, or copy/paste truncation.

**Evidence:** `evidence/b5_real_drive_20260809.txt`

**Needed to unblock:** Re-run OAuth consent against the **same** `GOOGLE_CLIENT_ID` currently in `.env` (redirect `http://localhost:8000/api/v1/connectors/google/callback`), with offline access, then replace `GOOGLE_REFRESH_TOKEN` with the newly issued refresh token and re-run:
```powershell
cd "D:\PROJECTS\Sync Ai Final\backend"
# load GOOGLE_* into $env: without printing
$env:EMBEDDING_PROVIDER = "fake"
& "..\..\.venv\Scripts\python.exe" -m pytest tests/test_b5_checkpoint_resume_real.py -v -s
```

### B5 Phase 2 — Real Google source PASS (2026-08-09)

**Account:** syncai740@gmail.com (Drive + Gmail scopes)  
**Token:** `GOOGLE_REFRESH_TOKEN` via OAuth Testing-status client — **expires ~2026-08-16** (7-day Google Testing-app limit). Re-run OAuth Playground / consent to renew after that date.  
**Credential wiring (actual Block B pattern):**
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` → pydantic settings (`google_client_id` / `google_client_secret`)
- User refresh token does **not** live in a DB vault by default; connectors read `TokenStore` key `google_oauth:{tenant_id}`
- Wired: `seed_token_store_from_env()` in `app/connectors/google/oauth.py` seeds that key from `GOOGLE_REFRESH_TOKEN`; Celery `DummyTokenStore` paths in `app/workers/tasks.py` call it after store creation
- Settings field: `google_refresh_token` / env `GOOGLE_REFRESH_TOKEN` in `app/core/config.py`

**Smoke test (before B5):** PASS — token refresh HTTP 200; Drive listed 1 file; Gmail listed 5 message IDs. Evidence: `evidence/b5_smoke_google_20260809.txt` (tokens redacted).

**B5 real-source run (Gmail, page_size=2):** PASS  
Drive had only 1 file (insufficient for multi-page kill); Gmail used for checkpoint resume.

| Metric | Value |
|--------|-------|
| Source | real Gmail API (`GmailConnector`) |
| Baseline pages / objects | **29 / 56** |
| Kill after | **14 / 29** pages (~50%) |
| Partial objects at kill | **28** |
| Checkpoint cursor at kill | `04252065523017696286` |
| Resume objects | **28** |
| Final objects | **56** (matches baseline; 0 dupes / 0 missing) |
| Baseline final cursor | `06593659312111574440` |

**Command:**
```powershell
cd "D:\PROJECTS\Sync Ai Final\backend"
# load GOOGLE_* into $env: without printing
$env:EMBEDDING_PROVIDER = "fake"
$env:B5_REAL_PAGE_SIZE = "2"
& "..\..\.venv\Scripts\python.exe" -m pytest tests/test_b5_checkpoint_resume_real.py -v -s
```

**Evidence:** `evidence/b5_real_gmail_checkpoint_20260809.txt`  
**Test:** `tests/test_b5_checkpoint_resume_real.py`  
**Independent reviewer:** still PENDING (§24.1).

