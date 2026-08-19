# Build Pass — Block M MCP Gateway (v5)

**Date:** 2026-08-17  
**Type:** Build + M1–M4. Named ACL-mock caveat carried, not fixed.  
**This file is not `SIGNOFF.md`.** Independent §24 rule-1 reviewer signoff is still required.

**HEAD:** `5ce77b1` — `Add: Block N completed and tested`  
**Branch:** `Pratham`  
**Repo:** `logicinnovationlabs/Sync-AI-Final`

`.env` / `backend/.env` were never opened. No commits, no pushes, no `SIGNOFF.md` edits. F–L / N / O were not modified (a new thin `app.services.query_federator` adapter was added so Block M does not HTTP-hop into J; J’s files were not edited).

---

## 5.1 Part A — fresh re-verification

```
git log -1 --oneline
```

```
5ce77b1 Add: Block N completed and tested
```

```
docker exec snyq_postgres psql -U postgres -d control_plane -c "\d tool_policies"
```

`tenant_id` = **`character varying(255)`** (also `server_name`, `tool_name`, `allowed`, UUID `id`).

```
docker exec snyq_postgres psql -U postgres -d control_plane -c "\d audit_logs"
```

`tenant_id` = **`character varying(255)`**. `id` and `actor_id` remain **uuid**.

```
grep -n "create_acl_checker(" backend/app --include="*.py" -r | grep -v test
```

```
backend/app/api/v1/document.py:31:acl_checker = create_acl_checker(settings)
backend/app/services/document_reader/acl_checker.py:97:def create_acl_checker(settings) -> MockACLChecker | HttpACLChecker:
```

Default `acl_backend` is still `"mock"` → **`MockACLChecker` on the real K path.** Named caveat, not a stop.

```
docker ps
```

`snyq_postgres` Up (healthy) `:5432`. Redis: `block-e-chunking-redis-1` on host `:6379` (`snyq_redis` not running). `python` Redis ping `localhost:6379` → **`True`**.

No contradiction with v2–v4. Build proceeded.

`pip show import-linter` → **Package(s) not found.** `importlinter-config.ini` was still created as specified. It is **not runnable** in this environment; CI will not enforce it until the package is installed.

---

## 5.2 What was built

| File | Role |
|------|------|
| `backend/app/services/mcp_gateway/__init__.py` | Exports router |
| `backend/app/services/mcp_gateway/identity.py` | JWT `tenant_id`/`sub` as strings via `deps.get_current_user`. No `tenant_resolver`. Impersonation (`user_id` / `tenant_id` ≠ JWT) → 403. `actor_id_for_audit`: UUID-shaped `sub` stored as-is; opaque principals (service-account client ids) → UUID5, raw value always in `target_json.user` — no `UUID("slug")` throw |
| `backend/app/services/mcp_gateway/allowlist.py` | Read-only `tool_policies` on `(tenant_id, server_name, tool_name)`. Missing row or `allowed=false` → reject |
| `backend/app/services/mcp_gateway/dispatch.py` | `search` → in-process federator; `read_document` → Block K `read_document` |
| `backend/app/services/mcp_gateway/audit.py` | One `audit_logs` row per POST, `action_type="mcp.tool_call"` (dotted, same family as `session.revoked`). `target_json`: host, client, user, tool, outcome, server_name |
| `backend/app/services/mcp_gateway/revocation.py` | Per-tenant cache, TTL = `tenant_cache_ttl_seconds` (default 1800). Subscribes to Redis `revocation_events` (`token_revoked` / `session_revoked`). No introspect polling |
| `backend/app/services/mcp_gateway/router.py` | `GET/POST /mcp/{server}` |
| `backend/app/services/query_federator/__init__.py` | **New thin adapter** calling J’s existing `_safe_call_*` helpers. J source files untouched |
| `backend/app/main.py` | `.bak` then mount + start/stop revocation listener in lifespan |
| `importlinter-config.ini` | Contracts as specified; package not installed |
| `backend/tests/test_block_m_signoff.py` | Replaced 404 placeholders with M1–M4 (`.bak` kept) |

ACL caveat at the K call site (`dispatch.py`):

```python
        # NOTE: Document reads delegate to Block K's document_reader, which
        # currently resolves to MockACLChecker (in-memory allow-set) on the
        # real request path, not app.acl.compiler's policy-derived decisions.
        # This is a known, separately-tracked gap — Block M does not introduce
        # a new permission model (architecture §15.1 rule 6), it inherits
        # whatever Block K enforces today. See BUILD_PASS_M_2026-08-17.md.
        import app.api.v1.document as document_routes
```

Tenant binding: string JWT claim straight into VARCHAR columns. No UUID cast.

---

## 5.3 M1–M4 results

**Phase: Phase 2** for identity, allowlist, audit, and revocation (real `control_plane` Postgres on `snyq_postgres`, real Redis on `:6379`, in-process J/K). Search backends may be empty/degraded; that does not change M2/M3/M4. Document-level ACL is **not** Phase-2 real policy (K mock).

```
python -m pytest tests/test_block_m_signoff.py -v --tb=short
```

```
tests/test_block_m_signoff.py::test_m1_no_service_account_escalation PASSED
tests/test_block_m_signoff.py::test_m2_non_allowlisted_tool_rejected PASSED
tests/test_block_m_signoff.py::test_m3_audit_completeness_20_calls PASSED
tests/test_block_m_signoff.py::test_m4_revoke_invalidates_within_60s PASSED
====================== 4 passed, 235 warnings in 19.66s =======================
```

| ID | Criterion | Result | Evidence / caveat |
|----|-----------|--------|-------------------|
| M1 | 20 SA-token impersonation attempts, 0 escalations | **PASS** | 20/20 HTTP 403. JWT identity is not replaced by `user_id` in the body. **Does not prove document-level ACL.** Content permission still follows K’s `MockACLChecker`. M1 here is tenant/user binding only |
| M2 | Non-allowlisted tool 100% rejected | **PASS** | `not_allowlisted_tool` (`allowed=false`) and a missing tool name both 403 before dispatch |
| M3 | 20 calls, complete audit (host, client, user, tool, outcome) | **PASS** | 10 allowlisted `search` + 10 rejected calls; `audit_logs.action_type='mcp.tool_call'` with those keys in `target_json` |
| M4 | Revoke via Block A `revocation_service.revoke_token` → next MCP call 401 ≤60s | **PASS** | Same bearer: 200 before revoke, **401** after; elapsed ≪ 60s (suite 19.66s total). Redis revoked-jti check + MCP cache |

---

## 5.4 Test `tool_policies` rows

Tenant slug **`mcp-m-test-tenant`** (not a production id). Persona `default`:

| tenant_id | server_name | tool_name | allowed |
|-----------|-------------|-----------|---------|
| mcp-m-test-tenant | default | search | t |
| mcp-m-test-tenant | default | read_document | t |
| mcp-m-test-tenant | default | not_allowlisted_tool | f |

Left in `control_plane` as labeled test data (pytest fixture also deletes/reinserts this tenant around each M test). Not org allowlist config.

---

## 5.5 Updated overall D–M status

D–L from prior reports, not re-run this session.

| Block | Phase 1 (mock) | Phase 2 (real infra) | Notes |
|-------|----------------|----------------------|--------|
| D–J | PASS (prior) | PASS (prior) | |
| K Reader | PASS (prior) | Not reached (MinIO) | Default ACL still `MockACLChecker` |
| L Orchestrator | PASS (prior) | Live OpenRouter (prior) | |
| N Admin | Commit says completed | `audit_logs` VARCHAR `tenant_id` after 004 | |
| **M Gateway** | n/a | **M1–M4 PASS this session** (pytest 4/4) | Module mounted. Document ACL inherited mock. import-linter not installed. Independent signoff still required |

---

## 5.6 Independent review

This report is evidence for a reviewer who is not the builder. It is **not** `SIGNOFF.md` and does not count as official integration under architecture §24 rule 1 until that reviewer signs.

Stopped here. No `SIGNOFF.md` edits, no N/O work, no commit, no push.
