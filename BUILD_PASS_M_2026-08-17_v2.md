# Build Pass — Block M observe follow-up: settle `acl_checker.py`, add `tool_policies`

**Date:** 2026-08-17  
**Type:** Diagnostic (acl_checker) + schema-only (`tool_policies`). No Block M code.  
**This file is not `SIGNOFF.md`.**

**HEAD:** `5ce77b1` — `Add: Block N completed and tested`  
**Branch:** `Pratham`  
**Repo:** `logicinnovationlabs/Sync-AI-Final`

`.env` / `backend/.env` were never opened. No commits, no pushes, no `SIGNOFF.md` edits. No `mcp_gateway/` code.

---

## 4.1 Part A — `acl_checker.py` diagnosis

### Command 1 — config defaults

```
grep -n "acl_service_url\|acl_backend" backend/app/core/config.py
```

```
469:    acl_backend: str = Field(default="mock")  # "mock" | "http"
470:    acl_service_url: str = Field(default="http://localhost:8000/api/v1/acl")
```

`.env.example` names only (file opened, not `backend/.env`): `ACL_BACKEND=mock`, `ACL_SERVICE_URL=http://localhost:8000/api/v1/acl`.

`HttpACLChecker` builds `{acl_service_url}/acl/compile`, so the default URL is:

`http://localhost:8000/api/v1/acl/acl/compile` (POST)

### Command 2 — does `app/api/v1/acl.py` expose `/acl/compile`?

No. The file is a debug GET only.

- Router prefix: `/acl`
- Mounted in `main.py` at `/api/v1` and also without prefix
- Sole route: `GET /{document_id}` → `GetACLResponse(document_id, tenant_id, entries)`
- No POST, no `/compile`

Real paths that exist: `GET /api/v1/acl/{document_id}` and `GET /acl/{document_id}`.

### Command 3 — `app/acl/compiler.py`

This **is** the real in-process Block C compiler. `ACLCompiler.compile()` materializes `ACLEntry` rows: direct grants, container inheritance, cycle-safe group expansion, then `_apply_deny_overrides` (deny wins over allow). It takes a `CanonicalDocument` plus permission hints. It does **not** implement query-time `is_allowed(tenant_id, principal_id, doc_id)` and it is **not** exposed as HTTP `/acl/compile`.

### Command 4 — who calls `create_acl_checker` on the real request path?

```
grep -rn "create_acl_checker\|acl_backend" backend/app --include=*.py | grep -v test
```

```
backend/app/api/v1/document.py:18:from app.services.document_reader.acl_checker import create_acl_checker
backend/app/api/v1/document.py:31:acl_checker = create_acl_checker(settings)
backend/app/api/v1/document.py:78:        settings.acl_backend,
backend/app/core/config.py:469:    acl_backend: str = Field(default="mock")  # "mock" | "http"
backend/app/services/document_reader/acl_checker.py:97:def create_acl_checker(settings) -> MockACLChecker | HttpACLChecker:
backend/app/services/document_reader/acl_checker.py:98:    if settings.acl_backend == "http":
backend/app/services/document_reader/__init__.py:10:from app.services.document_reader.acl_checker import ACLChecker, create_acl_checker
backend/app/services/document_reader/__init__.py:20:    "create_acl_checker",
```

`create_acl_checker(settings)` **is** on the real K request path (`document.py` module import). Default `acl_backend` is `"mock"`, so that path constructs `MockACLChecker`, not `HttpACLChecker`. `HttpACLChecker` is only built when `acl_backend == "http"`. Did not read `backend/.env` to see whether that was overridden; config default and `.env.example` are `mock`.

### Command 5 — response keys on the ACL route

```
grep -n "return\|JSONResponse\|response_model" backend/app/api/v1/acl.py
```

```
28:@router.get("/{document_id}", response_model=GetACLResponse)
36:    Tenant-scoped — only returns entries for the specified tenant.
55:        return GetACLResponse(
```

Returned keys: `document_id`, `tenant_id`, `entries`. None of `allowed` / `decision` / `access`.

### Settled diagnosis (which of the three scenarios)

**Scenario 2: the URL does not resolve to anything in this process.**

Not scenario 1 (HTTP-to-self drift): there is no `/acl/compile` route in this monolith, so `HttpACLChecker` is not calling the in-process compiler over HTTP.

Not scenario 3 as a live Block C contract bug: Block C never returns `allowed`/`decision`/`access`. The three-key fallback never sees a real compile body. If a GET accidentally hit `/{document_id}` with `document_id="compile"`, the body would be `{document_id, tenant_id, entries}` and `is_allowed` would fall through to `return False` (fail-closed). The constructed URL is also `.../acl/acl/compile` (double `acl`) and the method is POST, so the actual outcome under `acl_backend=http` is 404/405 → `HTTPException 500` “ACL service unavailable”, not a silent wrong-key parse.

**What this is not:** the F/G/H “second compiler without deny” defect. `HttpACLChecker` has no local allow-set. Deny support lives in `app.acl.compiler._apply_deny_overrides`. `MockACLChecker` **is** a separate in-memory allow-set used on the default K path (Phase 1 test double). That is intentional for K Phase 1; it is not a production compiler missing deny.

**Next-session fix (not this session):** do not point Phase 2 K at HTTP `/acl/compile`. Query-time allow must read compiled `ACLEntry` rows (or call a real in-process checker that does). `ACLCompiler.compile()` is a materializer, not a drop-in `is_allowed`.

No `acl_checker.py` code was changed this session.

---

## 4.2 Part B — `tool_policies` schema and apply

### Files added/edited (schema only; no read/write service)

| File | Action |
|------|--------|
| `backend/app/models/tool_policy.py` | **New.** `ToolPolicy` — UUID `id`/`tenant_id`, `server_name`, `tool_name`, `allowed`, timestamps. Unique `(tenant_id, server_name, tool_name)`. Indexes `ix_tool_policies_tenant_id` and `(tenant_id, server_name)`. |
| `backend/migrations/versions/003_tool_policies.py` | **New.** Revises `002_block_n_admin`. Same style as `audit_logs` in 002. |
| `backend/migrations/env.py` | Import `ToolPolicy` next to `AuditLog`. `.bak` taken before edit. |

No routes, no Block M module, no Block N writer.

`tenant_id` is PG UUID, matching `audit_logs` / control-plane `tenants`, not Block D’s VARCHAR content-key schema. JWT-string vs UUID remains the same dual contract N already has.

### Which Postgres — settled before apply

```
grep -n "sqlalchemy.url\|DATABASE_URL" backend/alembic.ini
```

```
6:sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/control_plane
```

(credentials already committed in `alembic.ini` / `docker-compose.yml`; not read from `.env`)

```
grep -n "DATABASE_URL\|database_url" backend/app/core/config.py
```

```
193:    control_plane_database_url: Optional[str] = Field(default=None)
474:        if not self.control_plane_database_url:
477:            self.control_plane_database_url = (
```

Assembled URL host is `settings.db_host`, port **5432**, database `settings.db_name`. `migrations/env.py` uses `settings.control_plane_database_url`, not the isolated Block D verify stack.

Root `docker-compose.yml` service `postgres`:

- `container_name: snyq_postgres`
- `POSTGRES_DB: control_plane`
- host port **5432** (`5432:5432`)

`block-d-verify-pg` is **:5435** / `block_d_verify`. Distinct instance. Not the alembic target.

**Decision:** apply to the main `postgres` service (`snyq_postgres`), not `block-d-verify-pg`.

### Instance health

```
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

`snyq_postgres` was **Up (healthy)** on `0.0.0.0:5432->5432/tcp`. `block-d-verify-pg` was also up on `:5435` and was not touched.

`snyq_app` / `snyq_migrate` were **not** running. Compose migrate uses `python -m alembic upgrade head` and `env_file: .env.docker`; that file is **absent**, so the compose migrate job cannot be the apply path here.

### Pre-apply state of `snyq_postgres` / `control_plane`

```
docker exec snyq_postgres psql -U postgres -d control_plane -c "\dt"
```

Only `orchestrator_memory` and `orchestrator_sessions`. **No `alembic_version`. No `audit_logs`.** 002 existed in the repo but had never been applied to this volume.

### Apply

Same command as compose migrate / README: `python -m alembic upgrade head`, from `backend/`. Host-side `alembic current` without a localhost override previously hit `OSError: [WinError 121]` (Settings DB host is not this published `localhost:5432`; value never printed). Process env `DB_HOST=localhost`, `DB_NAME=control_plane`, and `CONTROL_PLANE_DATABASE_URL` pointing at the **alembic.ini** host/port/db (`localhost:5432` / `control_plane`) so the connection matched the compose postgres mapping.

```
python -m alembic upgrade head
```

```
INFO  [alembic.runtime.migration] Running upgrade  -> 000_initial_schema, Initial schema - create all tables
INFO  [alembic.runtime.migration] Running upgrade 000_initial_schema -> 001_add_password_hash, Add password_hash column to users table
INFO  [alembic.runtime.migration] Running upgrade 001_add_password_hash -> 002_block_n_admin, Add Block N admin columns and tables.
INFO  [alembic.runtime.migration] Running upgrade 002_block_n_admin -> 003_tool_policies, Add tool_policies table for MCP persona allowlists.
```

Exit code 0. Because this volume had never been migrated, 000–002 ran in the same pass as 003. That is how `audit_logs` and `tool_policies` landed in the same database.

### Both tables visible on one connection

```
SELECT tablename FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('audit_logs', 'tool_policies')
ORDER BY 1;
```

```
   tablename
---------------
 audit_logs
 tool_policies
(2 rows)
```

```
SELECT version_num FROM alembic_version;
```

```
    version_num
-------------------
 003_tool_policies
(1 row)
```

`\d tool_policies` on the same `control_plane` database:

```
 id          uuid                     not null
 tenant_id   uuid                     not null
 server_name character varying(64)    not null
 tool_name   character varying(128)   not null
 allowed     boolean                  not null
 created_at  timestamptz              not null default now()
 updated_at  timestamptz              not null default now()
 PRIMARY KEY (id)
 INDEX ix_tool_policies_tenant_id (tenant_id)
 INDEX ix_tool_policies_tenant_id_server_name (tenant_id, server_name)
 UNIQUE uq_tool_policies_tenant_server_tool (tenant_id, server_name, tool_name)
```

### Test collection

```
python -m pytest tests/ --collect-only -q
```

```
161 tests collected, 5 errors in 4.32s
```

The five collection errors are **pre-existing** and unrelated to `ToolPolicy` / `env.py`:

| File | Error |
|------|--------|
| `test_block_c_advanced.py` | `ImportError: failed to find libmagic` |
| `test_mime_detector.py` | same `libmagic` |
| `test_pipeline_integration.py` | same `libmagic` |
| `test_signoff.py` | `cannot import name 'TokenExpiredError'` |
| `test_signoff_block_c.py` | `libmagic` |

Collected without error: `test_block_c_smoke.py::test_all_models_importable`, `test_block_n_signoff.py` (3), `test_block_m_signoff.py` (2, still 404 placeholders — no M routes added).

---

## Status (D–M, this session)

| Item | Result |
|------|--------|
| `acl_checker.py` HttpACLChecker | **Settled, not fixed.** Scenario 2: `/acl/compile` does not exist in-process. Default K path is `MockACLChecker`. |
| `tool_policies` schema + model | **Done.** |
| Applied on `snyq_postgres` `control_plane` | **Done.** Head = `003_tool_policies`. `audit_logs` and `tool_policies` both present. |
| `block-d-verify-pg` | **Not used.** |
| Block M gateway | **Not started.** |

Stopped here. No `SIGNOFF.md` edits, no M/N/O code, no commit, no push.
