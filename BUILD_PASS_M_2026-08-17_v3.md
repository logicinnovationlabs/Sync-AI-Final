# Build Pass — Block M MCP Gateway (v3): observe first, UUID-cast gate fired

**Date:** 2026-08-17  
**Type:** Observe-first. UUID-cast gate fired. No gateway code.  
**This file is not `SIGNOFF.md`.**

**HEAD:** `5ce77b1` — `Add: Block N completed and tested`  
**Branch:** `Pratham`  
**Repo:** `logicinnovationlabs/Sync-AI-Final`

`.env` / `backend/.env` were never opened. No commits, no pushes, no staging, no `SIGNOFF.md` edits. `backend/app/services/mcp_gateway/` was not created.

---

## 5.1 Part A — six command outputs and gate resolution

### Command 1 — which ACL checker runs on the real path

```
grep -n "acl_backend\|ACL_BACKEND" backend/app/core/config.py backend/.env.example
```

```
backend/app/core/config.py
469:    acl_backend: str = Field(default="mock")  # "mock" | "http"

backend/.env.example
156:ACL_BACKEND=mock
```

```
grep -rn "create_acl_checker(" backend/app --include="*.py" | grep -v test
```

```
backend/app/api/v1/document.py:31:acl_checker = create_acl_checker(settings)
backend/app/services/document_reader/acl_checker.py:97:def create_acl_checker(settings) -> MockACLChecker | HttpACLChecker:
```

`document.py` line 31 is the real request path. `create_acl_checker` returns `HttpACLChecker` only if `settings.acl_backend == "http"`; otherwise `MockACLChecker`. Default and `.env.example` are `"mock"`. `backend/.env` was not read.

**ACL gate:** known limitation, not a stop. If Part B had run, document reads through M would inherit the in-memory ACL mock until C/K wires the real compiler. Named, not fixed.

---

### Command 2 — JWT `tenant_id` at issuance

```
grep -n "tenant_id" backend/app/services/token_service.py | head -30
```

```
4:Critical for Signoff A1: every JWT contains exactly one tenant_id claim.
23:    Every token contains exactly one tenant_id claim (A1).
89:        tenant_id: str,
100:            tenant_id: Exactly one tenant UUID (A1)
119:            "tenant_id": tenant_id,  # A1: exactly one tenant_id
140:        tenant_id: str,
147:            tenant_id: Tenant UUID
161:            "tenant_id": tenant_id,
216:        tenant_id = payload.get("tenant_id")
217:        if jti and tenant_id:
218:            revoked = await redis_client.sismember(tenant_id, f"revoked:{jti}", jti)
226:        if tenant_id and principal_id is not None and tv_claim is not None:
227:            stored = await redis_client.get(tenant_id, f"token_version:{principal_id}")
235:        # A1: Ensure exactly one tenant_id
236:        if "tenant_id" not in payload:
237:            raise InvalidTokenError("Token missing tenant_id claim")
```

`issue_access_token` types `tenant_id` as `str`. The docstring says “tenant UUID”. The body copies the string into the claim with **no `UUID(...)` parse** on issue and **no UUID check** on `validate_token`. Any opaque string is a valid claim.

Production `/auth/login` does pass a control-plane UUID (`str(tenant.tenant_id)` from `app.models.tenant.Tenant`, PG_UUID). OAuth client-credentials uses `str(client.tenant_id)` (also UUID). That is the login path, not a platform invariant.

Counter-evidence that the claim is **not** always UUID-shaped:

- `backend/tests/conftest.py` `make_bearer(tenant_id, ...)` puts the argument into `tenant_id` with the same RS256 keys. K signoff uses `TENANT = "tenant-k"`.
- Lexical / vector / `get_document_tenant` treat the claim as an opaque `str` (the K-500 fix).
- `TokenService` will issue `"tenant-k"` if a caller passes it.

---

### Command 3 — Block D `tenants.tenant_id` vs control-plane `Tenant`

The prompt glob was `services/block-d-storage/migrations/*.py`. There is **no** `.py` migration there. The current migration is SQL:

```
services/block-d-storage/migrations/001_create_tenants_table.sql
6:CREATE TABLE IF NOT EXISTS tenants (
7:    tenant_id VARCHAR(255) PRIMARY KEY,
```

```
backend/app/models/tenant.py
22:class Tenant(Base, TimestampMixin):
32:    tenant_id: Mapped[UUID] = mapped_column(
```

Two tables named `tenants`, two types:

| Store | Column | Type |
|-------|--------|------|
| Block D (`001_create_tenants_table.sql`) | `tenants.tenant_id` | `VARCHAR(255)` |
| Control plane (`app.models.tenant.Tenant`) | `tenants.tenant_id` | `PG_UUID` |

Block D tests insert non-UUID values (`"d2_test_tenant"`, `"0"`, `"1"`, …).

---

### Command 4 — Redis revocation payload (full file)

`backend/app/services/revocation.py` publishes to Redis channel `revocation_events` (JSON):

**token_revoked**

```json
{
  "event_type": "token_revoked",
  "tenant_id": "<str>",
  "jti": "<str>",
  "timestamp": "<iso>"
}
```

**session_revoked**

```json
{
  "event_type": "session_revoked",
  "tenant_id": "<str>",
  "principal_id": "<str>",
  "timestamp": "<iso>"
}
```

Matches the assumed §3.5 shape (`session_revoked` / `token_revoked` on `revocation_events`). Not `session.revoked.v1` on Redpanda. **Revocation gate: does not fire.** If Part B ran, the listener would parse these keys, not the architecture-doc names.

`tenant_id` in the event is the same string passed into `revoke_*` (typed `str` in the service). No UUID guarantee there either.

---

### Command 5 — applied column types on `snyq_postgres` / `control_plane`

```
docker exec snyq_postgres psql -U postgres -d control_plane -c "\d tool_policies"
```

```
                      Table "public.tool_policies"
   Column    |           Type           | Collation | Nullable | Default
-------------+--------------------------+-----------+----------+---------
 id          | uuid                     |           | not null |
 tenant_id   | uuid                     |           | not null |
 server_name | character varying(64)    |           | not null |
 tool_name   | character varying(128)   |           | not null |
 allowed     | boolean                  |           | not null |
 created_at  | timestamp with time zone |           | not null | now()
 updated_at  | timestamp with time zone |           | not null | now()
```

```
docker exec snyq_postgres psql -U postgres -d control_plane -c "\d audit_logs"
```

```
                        Table "public.audit_logs"
   Column    |           Type           | Collation | Nullable | Default
-------------+--------------------------+-----------+----------+---------
 id          | uuid                     |           | not null |
 tenant_id   | uuid                     |           | not null |
 actor_id    | uuid                     |           | not null |
 action_type | character varying(100)   |           | not null |
 target_json | jsonb                    |           |          |
 ip_address  | character varying(64)    |           |          |
 created_at  | timestamp with time zone |           | not null | now()
```

Both `tenant_id` columns are **uuid**. `audit_logs.actor_id` is **uuid** as well (`sub` / principal is also `str` in the JWT, UUID in production login, slug in K fixtures).

---

### Command 6 — commit

```
git log -1 --oneline
```

```
5ce77b1 Add: Block N completed and tested
```

---

### Gate table

| Gate | Fired? | Resolution |
|------|--------|------------|
| ACL default is `MockACLChecker` | Yes (named caveat) | **Not a stop.** Carry forward: M document reads inherit K’s in-memory mock, not `app.acl.compiler`. |
| JWT `tenant_id` not confirmed UUID-safe | **YES — STOP** | Claim is `str` with no UUID validation. Block D `tenants.tenant_id` is `VARCHAR(255)`. `tool_policies` / `audit_logs` are `uuid`. Cast at M’s query boundary is not safe. |
| Redis payload ≠ assumed shape | No | `event_type` is `token_revoked` / `session_revoked`; channel `revocation_events`. |

---

## 5.2 UUID-cast gate — stop, no Part B

**What is true**

1. Control-plane `Tenant.tenant_id` and native/OAuth issuance **often** put a UUID string in the JWT.
2. That is not an invariant. `TokenService` does not enforce UUID. Content APIs bind the claim as an opaque string. Block D’s real `tenants.tenant_id` is `VARCHAR(255)` and is used with slugs. K’s live signoff tokens use `"tenant-k"`.
3. `tool_policies.tenant_id` and `audit_logs.tenant_id` (and `actor_id`) are PostgreSQL `uuid`. `UUID("tenant-k")` raises `ValueError: badly formed hexadecimal UUID string` — the same class of failure as K’s control-plane resolver 500.

**What Block M must not do (per this prompt)**

- App-side `try: UUID(claim) except: ...` fallbacks.
- Dual query paths (UUID vs string).
- Silently skip allowlist/audit when the cast fails.

**What would close the gate (not this session; not M’s job to pick alone)**

Either:

- **A.** Confirm every JWT `tenant_id` (and `sub`) is UUID-formatted at issuance — `TokenService` rejects non-UUID — **and** stop using slugs in content-API fixtures; or
- **B.** Follow-up migration: `tool_policies.tenant_id` and `audit_logs.tenant_id` (and likely `actor_id`) to `VARCHAR` matching Block D’s `tenants.tenant_id`.

Until A or B is chosen and applied, M2 (allowlist) and M3 (audit) cannot query/write those tables honestly for the same identity the content APIs use.

Part B was **not** entered. No `router.py`, no `main.py` mount, no `importlinter-config.ini`, no M1–M4 runs.

---

## 5.3 What was built

Nothing this session. Schema from v2 (`003_tool_policies`, `ToolPolicy` model) is unchanged.

---

## 5.4 M1–M4

Not run. Not labeled Phase 1 or Phase 2.

| ID | This session |
|----|----------------|
| M1 | **NOT RUN** |
| M2 | **NOT RUN** — allowlist table exists; tenant_id type mismatch blocks a honest query |
| M3 | **NOT RUN** — same mismatch on `audit_logs` |
| M4 | **NOT RUN** — Redis event shape is ready; no listener |

Inherited-ACL-mock caveat would apply to M1’s document-read path if M were built today: K still uses `MockACLChecker` on the default request path.

---

## 5.5 Updated overall D–M status

D–L from prior reports, not re-run this session.

| Block | Phase 1 (mock) | Phase 2 (real infra) | Notes |
|-------|----------------|----------------------|--------|
| D Storage | PASS (prior) | **PASS** (prior) | `tenants.tenant_id VARCHAR(255)` confirmed in current SQL migration |
| E Chunking | PASS (prior) | **PASS** (prior) | |
| F Lexical | PASS (prior) | **PASS** (prior) | JWT `tenant_id` as string |
| G Vector | PASS (prior) | **PASS** (prior) | JWT `tenant_id` as string |
| H Graph | PASS (prior) | **PASS** (prior) | |
| I Signals | PASS (prior) | **PASS** (prior) | |
| J Federator | PASS (prior) | **PASS** (prior) | |
| K Reader | **PASS** (prior) | **Not reached** | String JWT tenant. Default ACL = `MockACLChecker`. `HttpACLChecker` targets missing `/acl/compile` |
| L Orchestrator | PASS (prior) | Live OpenRouter (prior) | |
| N Admin | Commit says completed | `audit_logs` on `snyq_postgres` after v2 migrate | `tenant_id`/`actor_id` uuid |
| Q (K+L) | PASS (prior report) | Pending independent reviewer | |
| **M Gateway** | **BLOCKED** | **BLOCKED** | `tool_policies` exists. UUID-cast gate open. No module. |

**Bottom line:** Do not build M on a `UUID(jwt_tenant_id)` cast. Close the tenant-id type split (enforce UUID at issue, or migrate `tool_policies`/`audit_logs` to VARCHAR) first. ACL mock remains a named K/C caveat, not an M stop.

Stopped here. No `SIGNOFF.md` edits, no N/O work, no commit, no push.
