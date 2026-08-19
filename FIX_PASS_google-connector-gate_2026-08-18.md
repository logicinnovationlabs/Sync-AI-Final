# FIX PASS — Google Connector Pre-OAuth Gates
**Date:** 2026-08-18  
**Branch:** `Pratham`  
**Type:** Three narrow gates before Ach's manual Google login/consent. Not a signoff.  
**Does not overwrite:** `BUILD_PASS_google-connector_2026-08-18.md`  
**Does not touch:** `SIGNOFF.md`, OAuth authorize/callback, frontend, git commit/push.

---

## 6.1 Part A — Block C pipeline path is visible and fires

### What changed

Silent `try/except: return None` is gone. `process_raw_batch()` in `backend/app/connectors/google/pipeline_bridge.py` always logs a path marker:

- `pipeline=block_c` — Block C produced at least one `UnifiedDocument`
- `pipeline=fallback_transform` — Block C did not; includes `exc_type=` / `exc=` / a reason code

`backend/app/services/sync.py` copies the same markers into logs and into `stats["pipeline"]`. Fallback to `connector.transform()` is unchanged; it is no longer silent.

Root cause of the previous silent-fallback risk on this Windows host: `python-magic`/`libmagic` is not available. `mime_detector.py` used to fail at import, which made `from app.services.pipeline import Pipeline` explode, which the bare `except` swallowed. MIME detection now degrades to source-stated type with a warning, instead of taking down Block C.

### Real test batch — which path fired

Command:

```
python -m pytest tests/test_google_connector_gate.py::test_process_raw_batch_drive_fixture_uses_block_c tests/test_google_connector_gate.py::test_process_raw_batch_gmail_fixture_uses_block_c -q --tb=short --log-cli-level=INFO
```

Fixtures: `backend/tests/fixtures/google/drive/backfill_page1.json` and `.../gmail/backfill_page1.json`.

**Drive — Block C succeeded:**

```
WARNING  app.normalizer.mime_detector:mime_detector.py:17 python-magic/libmagic not available; MIME detection will trust source-stated type
INFO     app.normalizer.registry:registry.py:36 Registered normalizer strategy for google_drive: GoogleDriveNormalizer
INFO     app.identity.resolver:resolver.py:158 Created new principal ... for email owner@example.com ...
INFO     app.connectors.google.pipeline_bridge:pipeline_bridge.py:104 pipeline=block_c n=3 failed_items=0 source=google_drive tenant=d6a82a51-c58f-434b-818b-00007ec33a85
PASSED
```

**Gmail — Block C succeeded:**

```
INFO     app.connectors.google.pipeline_bridge:pipeline_bridge.py:104 pipeline=block_c n=3 failed_items=0 source=google_gmail tenant=79f6ec42-4af9-49fc-b5e8-d9e06e2d671b
PASSED
```

Result: **`pipeline=block_c`**, not fallback. Drive produced 3 unified docs (`failed_items=0`); Gmail produced 3 unified docs. Permissions on the Drive result used `user:` / `group:` prefixes (ACL compile ran).

Drive logged an identity error for the `anyone` / `*` “anyone with the link” hint. That did **not** drop the batch (`failed_items=0`). Named in §6.4 as out of scope.

---

## 6.2 Part B — Celery worker is listening on `celery` and `google`

### What was found

`docker ps` showed **no** `snyq_celery_worker` container (not running, not stopped). The only celery container up is `block-e-chunking-celery-worker-1`, which is Block E’s `embedding_worker`, not this app.

`docker-compose restart celery_worker` therefore could not apply: there is nothing to restart. Root compose’s worker depends on a healthy `app` container that is also not running; the API is already on the host (`uvicorn :8000`). Host Redis `:6379` is `block-e-chunking-redis-1` (the API already uses `redis://localhost:6379/1`).

Equivalent used: host worker against that broker, same `-Q celery,google` as compose.

### Startup logs (both queues)

```
 -------------- celery@Ishu v5.4.0 (opalescent)
-- ******* ---- Windows-11-10.0.26200-SP0 2026-08-18 10:02:42
- ** ---------- .> app:         snyq_backend:...
- ** ---------- .> transport:   redis://localhost:6379/1
- ** ---------- .> results:     redis://localhost:6379/1
- *** --- * --- .> concurrency: 1 (solo)
 -------------- [queues]
                .> celery           exchange=celery(direct) key=celery
                .> google           exchange=google(direct) key=google

[tasks]
  . app.workers.tasks.backfill_tenant_source
  . app.workers.tasks.google_queue_ping
  . app.workers.tasks.process_drive_notification
  . app.workers.tasks.process_gmail_notification
  . app.workers.tasks.renew_watch_channels

[2026-08-18 10:02:43,068: INFO/MainProcess] Connected to redis://localhost:6379/1
[2026-08-18 10:02:44,277: INFO/MainProcess] celery@Ishu ready.
```

### Real task picked up from `google`

Harmless task `app.workers.tasks.google_queue_ping` (routed to queue `google`). Sender:

```
task_id=b5ad02bd-21a9-496e-859d-aee03c269c36
result={'ok': True, 'queue': 'google'}
```

Worker:

```
[2026-08-18 10:02:54,262: INFO/MainProcess] Task app.workers.tasks.google_queue_ping[b5ad02bd-21a9-496e-859d-aee03c269c36] received
[2026-08-18 10:02:54,297: INFO/MainProcess] google_queue_ping: pipeline=queue_ok queue=google
[2026-08-18 10:02:54,302: INFO/MainProcess] Task app.workers.tasks.google_queue_ping[b5ad02bd-21a9-496e-859d-aee03c269c36] succeeded in 0.030999999995401595s: {'ok': True, 'queue': 'google'}
```

Earlier in this session the first worker start also drained leftover `backfill_tenant_source` jobs already sitting on `google` (tenant `df1da93d-...`, 0 indexed / 0 pages — expected with no OAuth token yet). That is additional proof the queue is consumed, not only that the name exists in compose.

The host worker is **left running** for Ach’s click, with the same Redis env the API already uses (`REDIS_URL=redis://localhost:6379`, broker `redis://localhost:6379/1`). Settings still default `redis_url` to the Docker hostname `redis`; without that override the token store logs `Redis unavailable (TimeoutError); vault-only`.

---

## 6.3 Part C — `seed_token_store_from_env` no longer clobbers a real token

### Purpose

Still a real local-dev / B5 bootstrap path. `backend/tests/test_b5_checkpoint_resume_real.py` documents it and calls it against an **empty** in-memory store when `GOOGLE_REFRESH_TOKEN` is set. Call sites remain in `backend/app/workers/tasks.py` (backfill + Drive/Gmail notify). Not leftover-only scaffolding, so the function was **not** removed.

### Fix applied: skip-if-token-exists (not remove)

If `token_store.get_token(google_oauth:{tenant_id})` already has a `refresh_token` or `access_token`, the function logs and returns `False` without writing. It only seeds when nothing is stored.

Live env check (names/booleans only, values not printed): `google_refresh_token` **is unset** in this process. The landmine is closed even if that var is later set.

### Real test — stored token survives backfill

```
python -m pytest tests/test_google_connector_gate.py::test_seed_does_not_clobber_existing_token tests/test_google_connector_gate.py::test_backfill_path_does_not_clobber_stored_token -q --tb=short --log-cli-level=INFO
```

Direct seed with `GOOGLE_REFRESH_TOKEN=env-refresh-token-must-not-win` and a pre-stored sentinel:

```
INFO     app.connectors.google.oauth:oauth.py:273 seed_token_store_from_env: skip, token already stored for tenant (will not clobber)
PASSED
```

Full `backfill_tenant_source(...)` entry (same env var set, sync patched to a no-op so this does not hit Google):

```
INFO     app.workers.tasks:tasks.py:110 Starting backfill for tenant 3ab224e6-13b0-4205-9a1b-5676d3f917b0, source google_drive
INFO     app.connectors.google.oauth:oauth.py:273 seed_token_store_from_env: skip, token already stored for tenant (will not clobber)
INFO     app.workers.tasks:tasks.py:197 Backfill completed for tenant 3ab224e6-13b0-4205-9a1b-5676d3f917b0, source google_drive: 0 indexed, 0 deleted, 0 pages
PASSED
```

Asserted after the backfill: stored `access_token` / `refresh_token` still the sentinels `real-oauth-*-sentinel`; env value did not win.

Empty-store bootstrap (B5) is unchanged: skip only runs when a token is already present.

---

## 6.4 Ready-for-OAuth confirmation

**All three gates are closed. Ach can proceed with the manual Google login/consent step.**

Host worker `celery@Ishu` is currently listening on `-Q celery,google` against `redis://localhost:6379/1`. API is already on `:8000`. After Connect, look for `pipeline=block_c` (or a loud `pipeline=fallback_transform` with `exc_type`) in worker logs — the silent path is gone.

### Named, not fixed (out of scope)

- No `snyq_celery_worker` container exists on this machine; the verified worker is a host process, not `docker-compose restart`.
- `:6379` is shared with `block-e-chunking-celery-worker-1`. Worker logs `mingle: sync with 1 nodes` and a ~6h clock drift warning against `celery@c17113b6b845`. That neighbor is a different app.
- `python-magic`/`libmagic` missing on this Windows host; MIME detection trusts source-stated type. Block C still ran.
- Drive fixture logs `Cannot resolve identity hint ... external_id=anyone` / email `*`. Documents still emerged (`failed_items=0`).
- `CanonicalRepo(use_memory=True)` is unchanged from the prior build report.
- Default `redis_url` still uses Docker DNS `redis`. Host processes must keep `REDIS_URL=redis://localhost:6379` (API already does; the worker started this session does too).
