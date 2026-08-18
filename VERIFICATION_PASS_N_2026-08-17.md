# Independent Verification Pass — Block N (Admin, Audit, and Governance Console)

**Date:** 2026-08-17  
**Type:** Read-and-report only. Same discipline as the original D–J verification pass. **This file is not `SIGNOFF.md`.** No criteria were marked in any `SIGNOFF.md`. No code was patched.

**Commit tested (HEAD, uncommitted D–M work on top):** `5ce77b1a97f3bf0ea0ba980282940f517e7ad911` (`Add: Block N completed and tested`)  
**Branch:** `Pratham`  
**Repo:** `logicinnovationlabs/Sync-AI-Final`

Python actually used:

```
C:\Users\Ishu Raj\AppData\Local\Python\pythoncore-3.14-64\python.exe
pytest-9.1.1  /  Python 3.14.0
```

`.env` / `backend/.env` were never opened. Env var **names** only: `CONTROL_PLANE_DATABASE_URL`, `TEST_DATABASE_URL`, `REDIS_URL`, `SESSION_STORE_REDIS_URL`, `VAULT_URL`. All five were **unset** in the shell before this pass set `TEST_DATABASE_URL` / `REDIS_URL` / `SESSION_STORE_REDIS_URL` for the pytest process (host/port/database names below; compose-declared role, password not printed).

No commits, no pushes, no staging, no `SIGNOFF.md` edits. `docker-compose config` was not used.

Architecture reference `Glean Arch made by Glean v1.3.1` is **not in this tree** (same as the D–J pass). N1–N3 wording below is taken from this session’s prompt (§24 signoff table as quoted there).

---

## 1. What’s actually there (pull/confirm)

```
On branch Pratham
Your branch is up to date with 'origin/Pratham'.
5ce77b1 Add: Block N completed and tested
origin  https://github.com/logicinnovationlabs/Sync-AI-Final.git (fetch)
origin  https://github.com/logicinnovationlabs/Sync-AI-Final.git (push)
```

```
git rev-parse HEAD
5ce77b1a97f3bf0ea0ba980282940f517e7ad911
```

Local `HEAD` **is** `5ce77b1`. No fetch / fast-forward was performed.

Uncommitted changes from prior D–M sessions are present (working tree dirty). The pull rule said: if uncommitted changes exist, **stop and do not force a merge**. Nothing was merged. The suite was run against this working tree, not a clean checkout of `5ce77b1`.

**Relevant dirty file for N:** `backend/app/models/audit_log.py` (uncommitted, 2 lines):

```
-    tenant_id: Mapped[UUID] = mapped_column(
-        PG_UUID(as_uuid=True),
+    tenant_id: Mapped[str] = mapped_column(
+        String(255),
```

That change is the on-disk model for `004_tenant_id_varchar` (untracked migration; alters `audit_logs.tenant_id` and `tool_policies.tenant_id` to `VARCHAR(255)`). `backend/tests/test_block_n_signoff.py` itself is **unmodified** vs `5ce77b1`.

---

## 2. Phase 1 vs Phase 2 — fixture evidence (do not trust the docstring)

Docstring of `backend/tests/test_block_n_signoff.py`:

```
"""Block N: Full Signoff Tests (N1, N2, N3) – runs against real Docker via service layer."""
```

### What `test_db` actually constructs

`backend/tests/conftest.py` `test_db`:

- `create_async_engine(TEST_DATABASE_URL, … poolclass=NullPool)` with default `postgresql+asyncpg://…@localhost:5432/control_plane`
- Per test: `Base.metadata.drop_all` then `create_all` on that engine
- Yields a real SQLAlchemy `AsyncSession`

This is **not** SQLite, **not** an in-memory dict store. It is a real asyncpg connection to Docker Postgres. Schema comes from SQLAlchemy `create_all` on the working-tree models, **not** from Alembic `002_block_n_admin`.

`redis_for_tests` (autouse): disconnects/reconnects the global `redis_client` and `ping`s. On success `_client` is a real `redis.asyncio.Redis`. On failure `connect()` swallows the exception and leaves `_client is None`; `set`/`get` then use an in-process `_fallback_store` dict (same class of silent double as K’s old in-memory store).

`vault_client` (used by the N helper to stash a tenant DB password): `get_vault_client()` returns **`MockVaultClient`** when `VAULT_URL` is blank. Confirmed at runtime (below). Vault is **not** a Block N signoff dependency, but the docstring’s “real Docker” claim does not cover it.

N1–N3 **do not** call FastAPI `/api/v1/admin/*`. They use:

| Test | What it actually drives |
|------|-------------------------|
| N1 | `native_auth_service.create_native_user` + **direct** `write_audit_log(...)` on `test_db`, 20 times, all `action_type="user.created"` |
| N2 | raw `INSERT … generate_series(1, 100000)` then `select(AuditLog).order_by(created_at.desc()).limit(50)` — **not** `GET /api/v1/admin/audit`, **not** a 90-day `date_from`/`date_to` filter |
| N3 | `redis_client.set(token_version:…)` in the test, then `token_service.validate_token` — **not** `POST /api/v1/admin/sessions/revoke` |

### Which instance this pass pointed at

Declared Block N deps in `backend/docker-compose.yml`: services `postgres` (`snyq_postgres`, host `:5432`) and `redis` (`snyq_redis`, host `:6379`). Full stack (qdrant / app / celery) was **not** started.

**Already running (not started this session):**

```
NAMES                              STATUS                 PORTS
snyq_postgres                      Up 2 hours (healthy)   0.0.0.0:5432->5432/tcp
block-e-chunking-redis-1           Up 2 hours (healthy)   0.0.0.0:6379->6379/tcp
block-d-verify-pg                  Up 2 hours (healthy)   0.0.0.0:5435->5432/tcp
… (other D–I verify containers; not used)
```

`snyq_postgres` `pg_isready -U postgres`: `accepting connections`.  
`pgcrypto` on `control_plane`: **0 rows** (`SELECT extname FROM pg_extension WHERE extname='pgcrypto'`). `SELECT gen_random_uuid()` still succeeded (Postgres 16 builtin; N2’s SQL would not have been blocked by the D4-style missing-extension gap).

Port `:6379` is **Block E’s** Redis, not `snyq_redis`. The autouse fixture `flushdb()`s whatever it connected to. Starting `snyq_redis` on `:6379` would conflict. This pass started a dedicated Redis so E would not be flushed:

```
NAMES                  STATUS        PORTS
block-n-verify-redis   Up            0.0.0.0:6389->6379/tcp
```

`test_db` defaults to database `control_plane` and **drops all tables every test**. To avoid wiping M’s `control_plane` rows, this pass created database `block_n_verify` on the **same** `snyq_postgres` container and set `TEST_DATABASE_URL` at the pytest process only. Same Docker Postgres, different database. Reported so it is not mistaken for the default URL.

### Pre-suite probe (same env as pytest)

```
redis_client_connected True
redis_client_class Redis
redis_url_host_port_only localhost:6389
redis_ping True
redis_fallback_keys 0
pg_current_database block_n_verify
gen_random_uuid_ok True
pgcrypto_installed 0
vault_client_class MockVaultClient
```

**Phase determination:**

- **Postgres:** Phase 2 (real `snyq_postgres` / `block_n_verify`, asyncpg).
- **Redis:** Phase 2 (real `block-n-verify-redis` `:6389`; `_client` is `Redis`, fallback unused).
- **Vault:** Phase 1 (`MockVaultClient`).
- **HTTP admin console:** **not exercised** by this suite.
- **Block A token check (N3):** real `token_service.validate_token` (same function `get_current_user` calls in `backend/app/api/deps.py`). Not a stub. Revoke **write** path is the test’s own `redis_client.set`, not `sessions.revoke_sessions`.

This is the same class of docstring-vs-reality gap as K’s “real K” in-memory store: the file says “real Docker via service layer”; Docker Postgres/Redis are real; the admin HTTP surface and 20 distinct console actions are not what the tests drive.

---

## 3. Suite result

Command (cwd `backend/`):

```
python -m pytest tests/test_block_n_signoff.py -v --tb=line
```

```
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Ishu Raj\AppData\Local\Python\pythoncore-3.14-64\python.exe
collected 3 items

tests/test_block_n_signoff.py::test_n1_audit_completeness FAILED         [ 33%]
tests/test_block_n_signoff.py::test_n1_audit_completeness ERROR          [ 33%]
tests/test_block_n_signoff.py::test_n2_audit_latency FAILED              [ 66%]
tests/test_block_n_signoff.py::test_n2_audit_latency ERROR               [ 66%]
tests/test_block_n_signoff.py::test_n3_revocation_propagation PASSED     [100%]
tests/test_block_n_signoff.py::test_n3_revocation_propagation ERROR      [100%]

==================== 2 failed, 1 passed, 3 errors in 3.79s ====================
```

First full run (`--tb=short -s`): **2 failed, 1 passed, 3 errors in 5.41s**. Same three outcomes.

### N1 / N2 root cause (working-tree 004 vs tests that still bind UUID)

`write_audit_log` / N2 bulk insert pass `tenant.tenant_id` as a **UUID**. Working-tree `AuditLog.tenant_id` is **VARCHAR**. asyncpg refuses the bind.

This is the collision `BUILD_PASS_M_2026-08-17_v4.md` already named (“`write_audit_log` still type-hints `tenant_id: UUID` … aligning the hint is N’s follow-up”) — now observed as a real suite failure, not a comment.

Not re-run against a clean `5ce77b1` tree (that would require reverting uncommitted files; out of scope). On committed `5ce77b1` the column was UUID and these two tests might have gotten past the bind; that is a counterfactual, not evidence.

### Full pasted failures / errors

**N1 FAIL** — insert of the first `user.created` audit row:

```
E   sqlalchemy.exc.DBAPIError: (sqlalchemy.dialects.postgresql.asyncpg.Error)
    <class 'asyncpg.exceptions.DataError'>: invalid input for query argument $2:
    UUID('0d6d873c-67da-4cb5-adb3-6ce5dad35d... (expected str, got UUID)
    [SQL: INSERT INTO audit_logs (id, tenant_id, actor_id, action_type, target_json, ip_address)
          VALUES ($1::UUID, $2::VARCHAR, $3::UUID, $4::VARCHAR, $5::JSONB, $6::VARCHAR)
          RETURNING audit_logs.created_at]
    [parameters: (UUID('94646a46-…'), UUID('0d6d873c-…'), UUID('a15136f0-…'),
                  'user.created', '{"principal_id": "d359db29-…"}', '127.0.0.1')]
```

**N1 ERROR at teardown** — `PendingRollbackError` wrapping the same insert (session left aborted; fixture then tries `delete(AuditLog).where(AuditLog.tenant_id == tenant.tenant_id)`).

**N2 FAIL** — 100k bulk insert never ran:

```
E   sqlalchemy.exc.DBAPIError: … expected str, got UUID
    [SQL: INSERT INTO audit_logs (id, tenant_id, actor_id, action_type, target_json, ip_address, created_at)
          SELECT gen_random_uuid(), $1, CAST($2 AS uuid), 'test.bulk',
                 jsonb_build_object('idx', idx), '127.0.0.1',
                 NOW() - (interval '1 second' * idx)
          FROM generate_series(1, 100000) AS idx]
    [parameters: (UUID('27dd81d9-…'), '38441406-…')]
```

p95 was **never measured**. The SQL also stamps `NOW() - (1 second * idx)` → span ≈ 1.16 days, not 90 days, and the timed query is `ORDER BY created_at DESC LIMIT 50` with **no date window**.

**N2 ERROR at teardown:**

```
[SQL: DELETE FROM audit_logs WHERE audit_logs.tenant_id = $1::VARCHAR]
[parameters: (UUID('27dd81d9-…'),)]
```

**N3 pytest body PASSED**, then **ERROR at teardown** (same VARCHAR `DELETE`):

```
[SQL: DELETE FROM audit_logs WHERE audit_logs.tenant_id = $1::VARCHAR]
[parameters: (UUID('e5f2a22c-…'),)]
```

N3 body: issue JWT → `validate_token` succeeds → `redis_client.set(…, token_version:principal, "1", ex=60)` → `validate_token` raises `RevokedTokenError`. Immediate in-process; `ex=60` is Redis key TTL, not a 60s wait. Console route `POST /api/v1/admin/sessions/revoke` is not called. `revocation_service.revoke_session` is not called.

---

## 4. Row-by-row (architecture criteria)

| ID | Architecture criterion | Phase | Result | One-line evidence |
|----|------------------------|-------|--------|-------------------|
| N1 | 20 distinct admin actions → 100% produce audit records | **2 (Postgres)** attempted | **FAIL** | Insert dies `expected str, got UUID` on `audit_logs.tenant_id VARCHAR`; test would have written 20 identical `user.created` rows via `write_audit_log` anyway, not 20 distinct console actions |
| N2 | 90-day audit window, representative volume, p95 ≤5s | **2 (Postgres)** attempted | **FAIL** | 100k insert never executed (same UUID bind); even as written: ~1.16-day timestamps, `LIMIT 50`, no `/admin/audit` |
| N3 | Revoke a session **from the console** → reflected in Block A within ≤60s | **2 (Redis + real `validate_token`)** | **FAIL** (criterion) / pytest body **PASSED** | Real Redis + real Block A `token_service.validate_token`; revoke was test-side `redis_client.set`, not `POST /admin/sessions/revoke`; no 60s clock; teardown ERROR |

---

## 5. `SIGNOFF.md` discrepancy

Checked (do not exist — `Test-Path` False):

- `backend/SIGNOFF.md`
- `backend/app/services/admin/SIGNOFF.md`
- `backend/app/api/v1/admin/SIGNOFF.md`

Repo `SIGNOFF.md` files that **do** exist are D–J service folders plus `backend/app/services/mcp_gateway/SIGNOFF.md` (Block M). **No Block N signoff file.**

Side by side (nothing resolved):

| Claim | Source | This pass |
|-------|--------|-----------|
| “Add: Block N completed and tested” | git `5ce77b1` subject | Suite: 2 failed, 1 passed, 3 errors on real Postgres/Redis |
| “runs against real Docker via service layer” | `test_block_n_signoff.py` docstring | Postgres/Redis: real. Vault: mock. Admin HTTP: not used. N1 writes its own audit rows. |
| N1 20 distinct admin actions, 100% audited | prompt / docstring | Not executed; would have been 20× `user.created` via helper |
| N2 90-day window p95 ≤5s | prompt / docstring | Not executed; query as written is not a 90-day window |
| N3 console revoke → Block A ≤60s | prompt / docstring | Block A `validate_token` is real; console revoke is not called; no timing |

`users.tenant_id` is still `UUID` in `backend/app/models/user.py`. 004 only widened `audit_logs` / `tool_policies`. Mixed types are on disk.

---

## 6. Scope coverage vs architecture Block N

Prompted scope: tenant admin **UI**, connector management, OAuth client management, audit search, session revocation, policy config. Interfaces: `/admin/*` **UI** + REST APIs.

**No frontend** in this repo (no `tsx`/`jsx`/`vue`/`html` admin app). No `admin-console` / `frontend` / `web` tree.

REST that **is** mounted (`backend/app/main.py`: `admin_router` at `/api/v1` + bootstrap at `/admin`):

| Surface | Present? | Notes |
|---------|----------|--------|
| Tenant bootstrap | **REST only** | `POST /admin/tenants` (unauthenticated chicken-and-egg) |
| User admin | **REST only** | `/api/v1/admin/users` invite / list / patch / deactivate / reset-password; audits `user.created`, `user.updated`, `user.deactivated`, `user.password_reset` |
| Connector management | **REST only** | `/api/v1/admin/connectors` upsert / list / delete; secrets via `vault_client` (mock when `VAULT_URL` blank) |
| Audit search | **REST only** | `GET /api/v1/admin/audit` (`date_from` / `date_to` / `action_type`, page ≤100). **Not** used by `test_n2_*` |
| Session revocation | **REST only** | `POST /api/v1/admin/sessions/revoke` bumps `token_version` in Redis then DB. **Not** used by `test_n3_*` |
| OAuth client management | **Missing** under `/admin/*` | `oauth_clients` table is Block A. `backend/app/api/v1/oauth.py` token grants return **501** stubs (`client_credentials` / `refresh_token` / `authorization_code` “not yet implemented”). No admin CRUD for clients |
| Policy config | **Missing** | No `/admin/config`. Contract mock `tests/mocks/contract_mock_server.py` and provisional `tests/test_blocks/test_block_n.py` expect `GET /admin/config`; that route is not on the real app. `tool_policies` exists from Block M; comments say “Block N is the only writer”; **no N writer route** in `backend/app/api/v1/admin/` |
| Tenant admin **UI** | **Missing** | REST only |

Admin action types that **production routes** know how to audit (not what N1 tests): `user.created`, `user.updated`, `user.deactivated`, `user.password_reset`, `connector.enabled` / `connector.updated`, `connector.removed`, `session.revoked`. That is fewer than 20 distinct types, and N1 never hits these routes.

A separate provisional suite `tests/test_blocks/test_block_n.py` talks to a **contract mock** (`/admin/audit`, `/admin/config`, SCIM). **Not run** this session (prompt named `backend/tests/test_block_n_signoff.py` only). Different N1/N2/N3 meanings.

---

## 7. Updated overall D–N status (Phase 1 / Phase 2)

D–L from prior verification reports, not re-run this session. M from `BUILD_PASS_M_2026-08-17_v6.md` (build pass, **not** an independent N-style verification). K storage Phase 2 is taken from `VERIFICATION_PASS_K-Phase2_2026-08-17.md`, not from M v6’s stale “K Phase 2 not reached” row.

| Block | Phase 1 (mock / test double) | Phase 2 (real infra) | Notes |
|-------|------------------------------|----------------------|--------|
| D Storage | PASS (prior) | **PASS** (prior) | Verify compose `block-d-verify-pg` `:5435` / MinIO `:9000` |
| E Chunking | PASS (prior) | **PASS** (prior) | Redis on `:6379` still held by `block-e-chunking-redis-1` this session |
| F Lexical | PASS (prior) | **PASS** (prior) | |
| G Vector | PASS (prior) | **PASS** (prior) | |
| H Graph | PASS (prior) | **PASS** (prior) | |
| I Signals | PASS (prior) | **PASS** (prior) | |
| J Federator | PASS (prior) | **PASS** (prior) | |
| K Reader | PASS (prior session, in-memory store) | **PASS** (K-Phase2, 7/7, MinIO+Postgres) | ACL still `MockACLChecker` |
| L Orchestrator | File-named 6/6; L1/L3/L4 architecture PASS (prior) | **L2 PASS** against Phase 2 K (prior) | Chat adapter / `StubToolbox` caveats unchanged |
| M Gateway | n/a | **M1–M4 PASS (build v5)** | Independent §24 reviewer still required; import-linter proven v6, manual only; document ACL inherited mock |
| **N Admin** | Vault `MockVaultClient`; suite does not hit `/admin` HTTP | Postgres+Redis **reached**; N1–N2 **FAIL**; N3 pytest body **PASSED** then teardown **ERROR** | Docstring overstates “service layer”; 004 VARCHAR `audit_logs.tenant_id` vs UUID binds; no N `SIGNOFF.md`; UI / OAuth-client admin / policy-config missing |

**Bottom line:** Commit `5ce77b1` and the N docstring are not evidence of N1–N3. This session pointed the unmodified `test_block_n_signoff.py` at real Docker Postgres (`snyq_postgres` / `block_n_verify`) and real Redis (`block-n-verify-redis` `:6389`). N1 and N2 **FAIL** on `expected str, got UUID` before any completeness or p95 assertion. N3’s pytest assertion **PASSED** against real Block A `validate_token` + real Redis, but it does not revoke from the console and does not measure ≤60s, so the architecture row is **FAIL**. No Block N `SIGNOFF.md` exists to contradict or match; the commit message does not match what ran.

Stopped here. No fixes, no `SIGNOFF.md` edits, no Block O, no commit, no push.
