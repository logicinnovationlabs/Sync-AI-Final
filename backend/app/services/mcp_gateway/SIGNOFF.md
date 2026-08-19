# Block M: MCP Gateway — Signoff

Per architecture §24 (Block M signoff table) and the independent-reviewer packet of 2026-08-17.

**This is the §24 rule-1 review.** Reviewer is not the engineer who built the module. Prior `BUILD_PASS_M_*.md` files were treated as claims, not as evidence.

| Field | Value |
|-------|--------|
| Date | 2026-08-17 |
| Reviewer | Independent reviewer (Cursor session 2026-08-17; no prior build-session memory; did not author the gateway) |
| Builder reports (claims only) | `BUILD_PASS_M_2026-08-17.md` … `_v6.md` |
| HEAD | `5ce77b1` — `Add: Block N completed and tested` |
| Branch | `Pratham` |
| Fixtures | Tenant `mcp-m-test-tenant`, persona `default`, tools `search` (allowed), `read_document` (allowed), `not_allowlisted_tool` (denied). JWT via `tests.conftest.make_bearer` (RS256). |
| Environment | Windows / PowerShell. `snyq_postgres` healthy `0.0.0.0:5432->5432` db `control_plane`. Redis `localhost:6379` (`block-e-chunking-redis-1`, ping True). Suite: `python -m pytest tests/test_block_m_signoff.py -v --tb=long` from `backend/`. |

**Block signoff: PASS** (M1–M4 all PASS under this session’s reproduction). Binary rule: no “mostly.”

---

## Signoff table

| ID | Criterion | Status | How verified this session |
|----|-----------|--------|---------------------------|
| M1 | Service-account / impersonation: 0 successful privilege escalations (20 attempts) | **PASS** | pytest `test_m1_no_service_account_escalation` + independent HTTP POST |
| M2 | Non-allowlisted tool on a persona endpoint is 100% rejected | **PASS** | pytest `test_m2_non_allowlisted_tool_rejected` + independent HTTP POST against real `tool_policies` rows |
| M3 | 20 tool calls produce complete audit (host, client, user, tool, outcome) | **PASS** | pytest `test_m3_audit_completeness_20_calls` + independent 20 calls + `psql` sample of `audit_logs` |
| M4 | Revoke (Block A) → next MCP call rejected within 60s | **PASS** | pytest `test_m4_revoke_invalidates_within_60s` + independent `revocation_service.revoke_token` timed at 0.0059s → HTTP 401 |

---

## Environment (this session, not assumed from prior reports)

```
git log -1 --oneline
5ce77b1 Add: Block N completed and tested
```

```
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Relevant rows: `snyq_postgres` Up 2 hours (healthy) `:5432`; `block-e-chunking-redis-1` Up 2 hours (healthy) `:6379`. `python` Redis ping → `True`.

Architecture PDF (`Glean Arch made by Glean v1.3.1`) is **not in this repo**. Criteria used are the §24 Block M rows as stated in the reviewer packet (M1 identity/escalation, M2 allowlist, M3 audit completeness, M4 revoke ≤60s), checked against the live module and tests.

---

## Pytest (this session)

```
cd backend
python -m pytest tests/test_block_m_signoff.py -v --tb=long
```

```
tests/test_block_m_signoff.py::test_m1_no_service_account_escalation PASSED
tests/test_block_m_signoff.py::test_m2_non_allowlisted_tool_rejected PASSED
tests/test_block_m_signoff.py::test_m3_audit_completeness_20_calls PASSED
tests/test_block_m_signoff.py::test_m4_revoke_invalidates_within_60s PASSED
====================== 4 passed, 235 warnings in 31.41s =======================
```

---

## M1 — identity / no escalation

**Does the test match the criterion?** Yes, for JWT identity binding. It is not a weaker “status != 200” check.

- Loop `range(20)` POSTs to `/mcp/default`.
- Token `sub` = `sa-client-mcp-m-test` (SA-shaped principal), body + `arguments.user_id` = a victim UUID.
- Assertion: **every** response is HTTP 403, then `rejected == 20`.

Code path: `reject_impersonation` in `identity.py` compares body/args `user_id` to JWT `sub`; mismatch → 403 `"User impersonation denied"`. Identity is `deps.get_current_user` (JWT string `tenant_id` / `sub`), not a control-plane UUID resolver.

**Independent spot-check (this session, not pytest):**

```
INDEP_M1_status 403 {"detail":"User impersonation denied"}
```

**What M1 PASS does not cover (known limitation, not an M fail):**

- This is tenant/user **binding**, not document-level ACL. K still defaults to `MockACLChecker` (see caveats).
- OAuth `client_credentials` is still HTTP 501 (`backend/app/api/v1/oauth.py`). The suite mints an RS256 JWT with an SA-shaped `sub` via `make_bearer`, which is the identity the gateway actually enforces. That is the escalation scenario the code can reject today.

---

## M2 — allowlist

**Does the test match the criterion?** Yes. It does **not** mock `is_tool_allowed`. `m_seed` only points `ControlPlaneSessionLocal` at `TEST_DB_URL` (`localhost:5432/control_plane`) and inserts real `tool_policies` rows. `allowlist.py` runs `SELECT allowed FROM tool_policies WHERE tenant_id, server_name, tool_name`. Missing row or `allowed=false` → reject.

This session’s table before independent calls:

```
     tenant_id     | server_name |      tool_name       | allowed
-------------------+-------------+----------------------+---------
 mcp-m-test-tenant | default     | search               | t
 mcp-m-test-tenant | default     | read_document        | t
 mcp-m-test-tenant | default     | not_allowlisted_tool | f
(3 rows)
```

**Independent spot-check:**

```
INDEP_M2_denied 403 Tool not allowlisted
INDEP_M2_missing 403
```

---

## M3 — audit completeness

**Does the test match the criterion?** Yes. 10 allowlisted `search` + 10 denied `not_allowlisted_tool`, then a real SELECT on `audit_logs` for `action_type='mcp.tool_call'`, requiring ≥20 rows whose `target_json` contains `host`, `client`, `user`, `tool`, `outcome`.

Pytest fixture teardown deletes that tenant’s rows, so this session **re-drove 20 calls** and sampled Postgres directly:

```
docker exec snyq_postgres psql -U postgres -d control_plane -c "SELECT id, tenant_id, action_type, target_json, created_at FROM audit_logs WHERE tenant_id = 'mcp-m-test-tenant' ORDER BY created_at DESC LIMIT 5;"
```

```
 id                                   | tenant_id         | action_type   | target_json
--------------------------------------+-------------------+---------------+---------------------------------------------------------------------------------------------------------------------------------
 4fde59ea-…                           | mcp-m-test-tenant | mcp.tool_call | {"host": "testclient", "tool": "search", "user": "83cb2a76-…", "client": "block-m-independent-review", "outcome": "success", "server_name": "default"}
 440299b5-…                           | mcp-m-test-tenant | mcp.tool_call | {"host": "testclient", "tool": "not_allowlisted_tool", "user": "83cb2a76-…", "client": "block-m-independent-review", "outcome": "rejected", "server_name": "default"}
 530f4304-…                           | mcp-m-test-tenant | mcp.tool_call | {"host": "testclient", "tool": "not_allowlisted_tool", "user": "83cb2a76-…", "client": "block-m-independent-review", "outcome": "rejected", "server_name": "default"}
 42a56e86-…                           | mcp-m-test-tenant | mcp.tool_call | {"host": "testclient", "tool": "not_allowlisted_tool", "user": "83cb2a76-…", "client": "block-m-independent-review", "outcome": "rejected", "server_name": "default"}
 b8c5f8dc-…                           | mcp-m-test-tenant | mcp.tool_call | {"host": "testclient", "tool": "not_allowlisted_tool", "user": "83cb2a76-…", "client": "block-m-independent-review", "outcome": "rejected", "server_name": "default"}
```

All five sampled rows contain **host, client, user, tool, outcome**. Independent count: **24** `mcp.tool_call` rows, **24** complete (20 M3 + M1/M2/M4 extras).

---

## M4 — revocation ≤ 60s

**Does the test match the criterion?** The pytest calls Block A `revocation_service.revoke_token` **and also** `mcp_session_cache.apply_event(...)` in-process. That extra cache injection is stronger than “subscribe to the event” alone. It does not weaken the assertion: same bearer, 200 before, 401 after, elapsed ≤ 60s.

**Independent check (this session, no `apply_event`):** Block A `revoke_token` only (Redis `revoked:{jti}` + publish `revocation_events`). Next POST with the same bearer:

```
INDEP_M4_before 200 {"server":"default","tool":"search","outcome":"success",...}
INDEP_M4_after 401 {"error":{"code":"UnauthorizedError","message":"Token has been revoked: a039e7ea-2770-45f2-adda-5a782c8f56fc",...}}
INDEP_M4_elapsed_s 0.0059
```

0.0059s ≪ 60s. Rejection is via `token_service.validate_token` Redis membership (the path `get_current_user` already runs on every MCP call). Criterion met.

Note (not a fail): during the independent `TestClient` run the MCP Redis **listener** logged `Redis unavailable, cache-only mode`; revoke still 401’d because validation checks the revoked set directly. Search backends were degraded (`OpenSearchStore` import error; Qdrant `query_vector` TypeError) and returned empty `degraded: true` 200s — out of M’s criteria.

---

## Carried-forward caveats (limitations of coverage, not M blockers)

### 1. K document-read ACL is still `MockACLChecker` on the real path

Confirmed this session (not from a prior report):

- `backend/app/core/config.py`: `acl_backend: str = Field(default="mock")`
- `backend/app/services/document_reader/acl_checker.py`: `create_acl_checker` returns `MockACLChecker()` unless `acl_backend == "http"`
- `backend/app/api/v1/document.py:31`: `acl_checker = create_acl_checker(settings)`
- `backend/app/services/mcp_gateway/dispatch.py` document-read uses `document_routes.acl_checker` (same object), with an explicit NOTE that this is inherited K mock, not `app.acl.compiler`

M does not introduce a second permission model. M1 PASS is identity binding, not document ACL. **Not a Block M signoff blocker.**

### 2. import-linter is a working manual gate, not CI

No `.github/workflows/`, Makefile, or `.pre-commit-config.yaml` in this repo. Declared in `backend/requirements-dev.txt` (`import-linter==2.3`). Must be run by hand from `backend/`:

```
lint-imports --config <repo>/importlinter-config.ini
```

**This session’s three-step proof** (cwd `backend/`):

Clean-before (exit 0):

```
MCP gateway must not define its own ACL or auth implementation KEPT
MCP gateway reaches retrieval only through federator and reader KEPT
Contracts: 2 kept, 0 broken.
```

Broken (temporary `identity.py` import of `app.services.mcp_gateway.acl`; exit 1):

```
MCP gateway must not define its own ACL or auth implementation BROKEN
...
app.services.mcp_gateway.identity is not allowed to import app.services.mcp_gateway.acl:
-   app.services.mcp_gateway.identity -> app.services.mcp_gateway.acl (l.13)
```

Clean-after (probe reverted; exit 0): same as clean-before, 2 kept, 0 broken.

**Not a Block M signoff blocker** — M’s criteria do not require CI wiring. The contract does fire.

---

## Contradictions vs the six build reports

**None that change M1–M4.** This session’s pytest 4/4, independent HTTP checks, Postgres audit sample, timed revoke, MockACLChecker default, and import-linter catch/revert all corroborate the v5/v6 claims.

Notes that are **not contradictions**:

- M4 pytest injects `apply_event` in addition to Block A revoke; independent revoke without that injection still 401’d in 0.0059s.
- Search backends on this machine are degraded; M still returns 200 for allowlisted `search` with `degraded: true` (as v5 already named).
- Architecture PDF is not in-tree; review used the §24 table from the reviewer packet plus the live code.

Block Q (K+L) was **not** reviewed or signed.

---

## Final

| Block | Signoff |
|-------|---------|
| **M MCP Gateway** | **PASS** — 2026-08-17, independent reviewer |

No other files were intended to change. No commits, no pushes.
