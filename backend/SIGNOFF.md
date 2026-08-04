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

---

## Sign-Off

**Engineer:** Cursor Agent — 2026-08-04  
**Reviewer:** PENDING  
**Block A (A1–A5) closeout:** **PASS**
