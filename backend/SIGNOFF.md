# BLOCK A SIGNOFF REPORT

**Block:** A — Tenancy, Identity, and Auth Platform  
**Version:** 0.1.0  
**Date:** 2026-08-04  
**Engineer:** Cursor Agent  
**Reviewer:** PENDING  
**Environment:** Windows/PowerShell — `block-a-verify-pg` (postgres:16, port 5434) + Redis `localhost:6379`  

**Location note:** Block A code lives under `backend/` (not `services/block-a-auth`).

---

## Signoff Criteria Results

**Block signoff (this closeout): PASS only if A1–A5 all PASS** (master prompt §4.3). A6/A7 remain in the historical suite but are outside this closeout gate.

| ID | Criterion | Test Method | Pass Threshold | Result | Evidence |
|----|-----------|-------------|----------------|--------|----------|
| **A1** | Tenant binding integrity | Issue 100 tokens across 3 tenants (mixed interactive + service) | 100% exactly one `tenant_id`, signature + expiry valid | **PASS** | `tests/test_signoff_closeout_local.py::test_A1_*` — 100/100 ok, `kid=key-2026-08` |
| **A2** | Revocation latency | Revoke; poll `GET /api/v1/me` every 5s; 20 trials | 100% rejected within ≤60s | **PASS** | 20/20 trials, latency ~0.025–0.031s, status 401 |
| **A3** | SCIM idempotency | Sync 3× with **process restart** between runs | identical `principal_id`, 0 drift | **PASS** | 3 distinct PIDs `{28324,34096,5340}`; Okta-shaped fixture; identical UUIDv5 principals |
| **A4** | Cross-tenant replay rejection | Tenant-A token → tenant-B-scoped endpoints, 50 attempts | 50/50 401/403, 0 leaks | **PASS** | 50/50 status 403 via `X-Tenant-ID` mismatch |
| **A5** | Scope enforcement | Every scoped route, token missing required scope | 100% 403 in error envelope | **PASS** | 7/7 routes: connectors.* + scoped probes; `error.code` + `error.message` present |

| **A6** | Secret pointer (Vault) | (historical suite) | — | NOT IN THIS CLOSEOUT GATE | See `tests/test_signoff.py` |
| **A7** | Per-tenant cache isolation | (historical suite) | — | NOT IN THIS CLOSEOUT GATE | See `tests/test_signoff.py` |

---

## Overall Result

**PASS** — A1–A5 criteria passed this session against real Postgres:5434 + Redis.

---

## Test Execution Summary

**Command:**
```powershell
$env:SNYQ_IGNORE_ENV_FILE="1"
$env:JWT_PRIVATE_KEY_PATH="...\backend\keys\private.pem"
$env:JWT_PUBLIC_KEY_PATH="...\backend\keys\public.pem"
$env:TEST_DATABASE_URL="postgresql+asyncpg://postgres:verify@localhost:5434/block_a_verify"
$env:CONTROL_PLANE_DATABASE_URL="postgresql+asyncpg://postgres:verify@localhost:5434/block_a_verify"
$env:REDIS_URL="redis://localhost:6379"
python -m pytest tests/test_signoff_closeout_local.py -v -s
```

**Output (summary):**
```
A1 PASSED: 100/100 tokens contain exactly one tenant_id and pass validation
A2 PASSED: 20/20 trials rejected within <=60s
A3 PASSED: principal_id identical across 3 process restarts, 0 drift; pids={34096, 5340, 28324}
A4 PASSED: 50/50 cross-tenant replay attempts rejected, 0 leaks
A5 PASSED: 7/7 scoped endpoints returned 403 error envelope
====================== 5 passed, 367 warnings in 21.72s =======================
```

### A3 principal_ids (all 3 runs identical)
```
00u1okta-subject-alice -> cb0d57f6-1d5c-5835-8975-7c60cfee946d
00u1okta-subject-bob   -> 8b425e2a-15aa-5d1e-935c-69ddb4cc7b22
00u1okta-subject-carol -> 5a9dbaff-c3c3-5fea-9aff-ef2f366b875f
```

### A5 scoped route table exercised
```
POST /api/v1/connectors/{source_type}/backfill     connectors.write
GET  /api/v1/connectors/{source_type}/status       connectors.read
POST /api/v1/connectors/{source_type}/disconnect   connectors.write
GET  /api/v1/connectors/google/authorize           connectors.write
GET  /api/v1/scoped/search                         search.read
GET  /api/v1/scoped/documents                      document.read
GET  /api/v1/scoped/admin/audit                    admin.audit.read
```

---

## Schema introspection (this session)

- `tenants.db_secret_key` — Vault key **name/pointer**, not raw password
- No dedicated `sessions` table — session revocation uses `refresh_tokens` + Redis `tenant:{id}:revoked:{jti}`
- `oauth_clients` + `refresh_tokens` present after `Base.metadata.create_all` on `block_a_verify`

---

## Deviations from spec

1. **Service path:** Implemented under `backend/`, not `services/block-a-auth`.
2. **JWT key rotation (§14.4):** Structural support added (`kid` header, `register_verification_key` / `rotate_signing_key`, `jwt_active_kid`). Full dual-key PEM file lifecycle / JWKS endpoint not yet shipped.
3. **Session store:** No `sessions` table; TTL on Redis revoked sets still a no-op (`pass` in `revocation.py`). Access-token revoke is Redis jti set checked on every `validate_token`.
4. **OAuth token endpoint:** `POST /oauth/token` grant types still return 501; A1 issuance uses `TokenService` / native login path for closeout evidence.
5. **A4 tenant scoping:** Enforced via required `X-Tenant-ID` header matching JWT `tenant_id` on scoped probe routes (`require_matching_tenant`). Host/subdomain-based tenancy is not the mechanism under test here.
6. **A5 probe routes:** `search.read` / `document.read` / `admin.audit.read` exposed as `/api/v1/scoped/*` probes because those product routes are not otherwise present in Block A; connectors.* scopes come from the live route table.
7. **Shared verify DB:** A3 cleans Okta fixture `idp_subject` rows once before the 3 process runs because `users.idp_subject` / `email` are globally unique in the shared `block_a_verify` database (production assumes per-tenant DBs).
8. **Historical `test_signoff.py`:** Prior A2/A4/A5 tests were in-process simulations; closeout evidence is from `test_signoff_closeout_local.py` only.
9. **SCIM tenant-reassignment (closeout §2.1 — TEST-ONLY, removed):** Earlier `scim_sync_once.py` reassigned `user.tenant_id` when an `idp_subject` collision existed under a different tenant in the shared verify DB. That is **not** production behavior — a SCIM feed must not silently migrate identities across tenant boundaries (exploitable via misconfigured/malicious IdP feed). Production `scim_sync_service.sync_users` never reassigns `tenant_id`. The reassignment was removed from `scim_sync_once.py`; shared-DB collision handling stays solely in the A3 test cleanup (`delete` by fixture `idp_subject` before the 3 process runs).
10. **TenantMiddleware soft-fail (closeout §2.2 — intentional, narrowed):** Soft-fail is intentional because route-level auth deps are the real 401/403 gate and this middleware is optional pre-resolve only. Previously bare `except Exception: pass` was silent. Now: expected cases (`TenantNotFoundError`, `VaultError`, `jwt.PyJWTError`, `SQLAlchemyError`, `ValueError`, `KeyError`, `OSError`) log at DEBUG; any other exception still soft-fails (so pool/event-loop glitches cannot 500 the request before auth deps run) but logs at WARNING with exception type — not silent pass-through.
11. **A5 synthetic scoped probes — ACTION ITEM (closeout §2.3):** `/api/v1/scoped/*` exists only to exercise `search.read` / `document.read` / `admin.audit.read` until Blocks F/J/K ship real routes. **Re-run A5 against real `POST /api/v1/search` and `GET /api/v1/document/{id}` (and admin audit) once those exist; then retire the synthetic probes.** Tracked until Blocks J/K/N land.

---

## Closeout gap closure (2026-08-05)

### A3 re-run after removing tenant-reassignment from `scim_sync_once.py`
```
A3 run 1 pid=30568 principals={alice/bob/carol UUIDv5s identical}
A3 run 2 pid=16352 principals={same}
A3 run 3 pid=33084 principals={same}
A3 PASSED: principal_id identical across 3 process restarts, 0 drift; pids={30568, 16352, 33084}
1 passed in 2.70s
```
Principal IDs unchanged from prior closeout:
```
00u1okta-subject-alice -> cb0d57f6-1d5c-5835-8975-7c60cfee946d
00u1okta-subject-bob   -> 8b425e2a-15aa-5d1e-935c-69ddb4cc7b22
00u1okta-subject-carol -> 5a9dbaff-c3c3-5fea-9aff-ef2f366b875f
```
Log: `a3_rerun.log`.

### Full A1–A5 re-run after TenantMiddleware narrowing
```
A1 PASSED: 100/100 tokens contain exactly one tenant_id and pass validation
A2 PASSED: 20/20 trials rejected within <=60s
A3 PASSED: principal_id identical across 3 process restarts, 0 drift; pids={3520, 22900, 19088}
A4 PASSED: 50/50 cross-tenant replay attempts rejected, 0 leaks
A5 PASSED: 7/7 scoped endpoints returned 403 error envelope
======================= 5 passed, 367 warnings in 8.19s =======================
```
Log: `a1_a5_rerun2.log`. Deviations 9–11 recorded above.

---

## Sign-Off

**Engineer:** Cursor Agent — 2026-08-04 (gaps closed 2026-08-05)  
**Reviewer:** PENDING  
**Block A (A1–A5) closeout:** **PASS**
