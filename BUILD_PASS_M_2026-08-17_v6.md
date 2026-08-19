# Build Pass — Block M complete-integration (v6)

**Date:** 2026-08-17  
**Type:** Close two already-identified gaps only: import-linter enforcement + `tool_policies` test-data hygiene. No Block M logic changes.  
**This file is not `SIGNOFF.md`.** Independent §24 rule-1 reviewer signoff is still required.

**HEAD:** `5ce77b1` — `Add: Block N completed and tested`  
**Branch:** `Pratham`  
**Repo:** `logicinnovationlabs/Sync-AI-Final`

`.env` / `backend/.env` were never opened. No commits, no pushes, no staging, no `SIGNOFF.md` edits. F–L / N / O were not modified. Block M router / dispatch / allowlist / audit / revocation logic was not changed. K’s `MockACLChecker` caveat was not touched.

---

## 4.1 Import-linter: installed, proven, still manual

### Installation

`python -m pip show import-linter`:

```
Name: import-linter
Version: 2.3
Summary: Enforces rules for the imports within and between Python packages.
Location: C:\Users\Ishu Raj\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages
Requires: click, grimp, typing-extensions
```

Matched the existing dev-tooling pattern rather than an ad-hoc-only install:

- `backend/requirements-dev.txt` — `import-linter==2.3` (same pin style as `ruff` / `mypy`)
- `backend/pyproject.toml` `[tool.poetry.group.dev.dependencies]` — `import-linter = "^2.1"` (same group as `ruff` / `mypy`)

Both files were `.bak`’d before edit.

**CLI entry point:** `lint-imports` (`lint-imports.exe` under the Python 3.14 Scripts directory). `python -m importlinter` is **not** an entry point on this version. The Scripts directory is not on PATH in this shell, so the proven command is the full path to `lint-imports.exe`. It must be run with **cwd = `backend/`** because `root_packages = app`.

### Config adjustment (required for the contract to be a valid import-linter graph)

The v5 file used `source_modules = app.services.mcp_gateway` against `forbidden_modules = app.services.mcp_gateway.acl`. import-linter 2.3 rejects that as a **config error** (`Modules have shared descendants`), not as a named contract violation — which is the exact “file sitting in the repo” failure mode this session had to disprove.

`importlinter-config.ini` was `.bak`’d, then rewritten so `source_modules` are the **leaf** gateway modules (`router`, `dispatch`, `identity`, `allowlist`, `audit`, `revocation`). Forbidden targets stay `app.services.mcp_gateway.acl` / `.jwt_auth` / `.auth`. Same intent as §29.6; now a graph import-linter will actually check.

### Clean-before (0 violations)

```
& "...\Scripts\lint-imports.exe" --config "D:\PROJECTS\A sync Ai final\importlinter-config.ini"
```

cwd: `backend/`. Exit code **0**.

```
=============
Import Linter
=============

---------
Contracts
---------

Analyzed 159 files, 341 dependencies.
-------------------------------------

MCP gateway must not define its own ACL or auth implementation KEPT
MCP gateway reaches retrieval only through federator and reader KEPT

Contracts: 2 kept, 0 broken.
```

### Broken (deliberate §29.6 violation)

`.bak` of `backend/app/services/mcp_gateway/identity.py`, then:

1. Temporary `backend/app/services/mcp_gateway/acl.py` (`dummy = True`).
2. One added line in `identity.py`: `from app.services.mcp_gateway.acl import dummy`.

Re-run. Exit code **1**.

```
=============
Import Linter
=============

---------
Contracts
---------

Analyzed 160 files, 342 dependencies.
-------------------------------------

MCP gateway must not define its own ACL or auth implementation BROKEN
MCP gateway reaches retrieval only through federator and reader KEPT

Contracts: 1 kept, 1 broken.


----------------
Broken contracts
----------------

MCP gateway must not define its own ACL or auth implementation
--------------------------------------------------------------

app.services.mcp_gateway.identity is not allowed to import app.services.mcp_gateway.acl:

-   app.services.mcp_gateway.identity -> app.services.mcp_gateway.acl (l.13)


app.services.mcp_gateway.router is not allowed to import app.services.mcp_gateway.acl:

-   app.services.mcp_gateway.router -> app.services.mcp_gateway.identity (l.15)
    app.services.mcp_gateway.identity -> app.services.mcp_gateway.acl (l.13)
```

That is the named ACL/auth contract firing on the exact import that broke it — not a silent pass, not a config-error false negative.

### Clean-after

`identity.py` restored from `.bak`. `acl.py` deleted. Re-run. Exit code **0**.

```
=============
Import Linter
=============

---------
Contracts
---------

Analyzed 159 files, 341 dependencies.
-------------------------------------

MCP gateway must not define its own ACL or auth implementation KEPT
MCP gateway reaches retrieval only through federator and reader KEPT

Contracts: 2 kept, 0 broken.
```

Gateway directory after revert: `__init__.py`, `router.py`, `dispatch.py`, `identity.py`, `allowlist.py`, `audit.py`, `revocation.py`, plus `identity.py.bak`. No `acl.py`.

### Wired into an automated step? **No — still manual.**

Looked for: `.github/workflows/`, `Makefile` / `makefile`, `.pre-commit-config.yaml`, `tox.ini`, `noxfile.py`. **None exist** in this repo. `pytest.ini` / `backend/pyproject.toml` have pytest/ruff/mypy config only — no lint-imports hook.

Per session scope: do not invent a CI pipeline. `lint-imports --config importlinter-config.ini` (cwd `backend/`) has to be run **manually** until a CI or pre-commit mechanism exists to attach to. The package is now a declared dev dependency so that future hook can `pip install -r backend/requirements-dev.txt` and run the same command.

---

## 4.2 `tool_policies`: found synthetic, left as labeled test data

### What was there

```
docker exec snyq_postgres psql -U postgres -d control_plane -c "SELECT * FROM tool_policies;"
```

```
                  id                  |     tenant_id     | server_name |      tool_name       | allowed |          created_at           |          updated_at
--------------------------------------+-------------------+-------------+----------------------+---------+-------------------------------+-------------------------------
 b17748b3-5186-46f1-9c05-cf568eccd4a4 | mcp-m-test-tenant | default     | search               | t       | 2026-08-17 09:35:19.873915+00 | 2026-08-17 09:35:19.873915+00
 3e440131-50ba-4a66-831b-5f4b9503617f | mcp-m-test-tenant | default     | read_document        | t       | 2026-08-17 09:35:19.873915+00 | 2026-08-17 09:35:19.873915+00
 7027fefb-debf-4201-be68-9ba61ee14e6b | mcp-m-test-tenant | default     | not_allowlisted_tool | f       | 2026-08-17 09:35:19.873915+00 | 2026-08-17 09:35:19.873915+00
(3 rows)
```

### Assessment — already unambiguous; no rewrite, no delete

**Approach taken: keep the three rows.** They already meet the “obviously synthetic” bar in §3.2:

- `tenant_id` is `mcp-m-test-tenant` — contains `test`, names Block M, cannot pass for a production tenant slug.
- One tool is literally `not_allowlisted_tool` with `allowed = f` — that name is a verification fixture, not an org policy.
- These are the only rows in the table (Block N’s admin console is still the future real writer).

Deleting would also have been a safe empty-until-N state, but it would force an independent reviewer to re-seed before re-running M2. The existing naming already prevents mistaking this for forgotten production policy, so rewrite/delete was not needed.

### Final table state

Unchanged from the SELECT above: three rows, tenant `mcp-m-test-tenant`, tools `search` / `read_document` / `not_allowlisted_tool`.

---

## 4.3 Block M consolidated status (this session + prior five)

**What’s built** (v5, unchanged this session): `backend/app/services/mcp_gateway/` mounted in `backend/app/main.py` — JWT string identity, `tool_policies` allowlist, in-process federator/reader dispatch, `audit_logs` `mcp.tool_call`, Redis `revocation_events` listener. Thin `app.services.query_federator` adapter; J files not edited. `tool_policies.tenant_id` / `audit_logs.tenant_id` are VARCHAR(255) (migration 004).

**What passed** (v5, not re-run here): M1–M4 pytest **4 passed in 19.66s** on real `snyq_postgres` `control_plane` + Redis `:6379`.

| ID | Result (v5) |
|----|-------------|
| M1 | PASS — 20/20 impersonation 403. JWT binding only; **not** document ACL |
| M2 | PASS — non-allowlisted + missing tool 403 before dispatch |
| M3 | PASS — 20 `mcp.tool_call` rows with host/client/user/tool/outcome |
| M4 | PASS — revoke → next MCP call 401 well under 60s |

**Two gaps now closed (this session):**

1. import-linter **2.3 is installed**, declared in `requirements-dev.txt` / poetry dev extras, config is a valid graph, and the ACL/auth contract **fails on a real forbidden import and passes again after revert**. It is **not** wired into CI (none exists); it is a working **manual** build gate.
2. `tool_policies` rows are confirmed synthetic (`mcp-m-test-tenant` / `not_allowlisted_tool`) and left as labeled M2 fixtures.

**Two caveats still open, carried forward, not this session’s job:**

- K’s document-read ACL still resolves to `MockACLChecker` (`acl_backend="mock"` on the real K path), not `app.acl` policy-derived access control. Block M inherits that. Named in `dispatch.py`; still not fixed.
- Independent §24 rule-1 reviewer signoff has **not** happened. This report, like v1–v5, is evidence for that reviewer, not a substitute. `SIGNOFF.md` was not edited.

---

## 4.4 Updated overall D–M status

D–L from prior reports, not re-run this session.

| Block | Phase 1 (mock) | Phase 2 (real infra) | Notes |
|-------|----------------|----------------------|--------|
| D–J | PASS (prior) | PASS (prior) | |
| K Reader | PASS (prior) | Not reached (MinIO) | Default ACL still `MockACLChecker` — **still open** |
| L Orchestrator | PASS (prior) | Live OpenRouter (prior) | |
| N Admin | Commit says completed | `audit_logs` VARCHAR `tenant_id` after 004 | Not entered this session |
| **M Gateway** | n/a | **M1–M4 PASS (v5)** | Module mounted. import-linter **installed + proven** (v6); **manual only** (no CI/pre-commit in repo). `tool_policies` test rows confirmed synthetic. Document ACL inherited mock. Independent signoff still required |

---

Stopped here. No `SIGNOFF.md` edits, no N/O work, no commit, no push.
