# Build Pass — Block M unblock: `tenant_id` VARCHAR on `tool_policies` and `audit_logs`

**Date:** 2026-08-17  
**Type:** Schema-only. Closes the UUID-cast gate from `BUILD_PASS_M_2026-08-17_v3.md`. No Block M code.  
**This file is not `SIGNOFF.md`.**

**HEAD:** `5ce77b1` — `Add: Block N completed and tested`  
**Branch:** `Pratham`  
**Repo:** `logicinnovationlabs/Sync-AI-Final`

`.env` / `backend/.env` were never opened. No commits, no pushes, no `SIGNOFF.md` edits. No `mcp_gateway/` module.

---

## 6.1 Row counts and FKs before alter

`snyq_postgres` was **Up (healthy)** on `0.0.0.0:5432->5432/tcp`. Database `control_plane`.

```
SELECT count(*) FROM audit_logs;
```

```
 count
-------
     0
```

```
SELECT count(*) FROM tool_policies;
```

```
 count
-------
     0
```

Both empty. `USING tenant_id::text` would have preserved values if any existed; none did. No truncate-and-reload.

`\d+` on both tables: btree indexes on `tenant_id` (and composites). **No foreign keys** referencing `tool_policies.tenant_id` or `audit_logs.tenant_id`. Indexes do not pin a column type; they remained after `ALTER COLUMN`.

---

## 6.2 Migration applied

New file: `backend/migrations/versions/004_tenant_id_varchar.py`  
`down_revision = "003_tool_policies"`

`python -m alembic upgrade head` from `backend/` against `snyq_postgres` / `control_plane` (same host/port/db as alembic.ini / compose `postgres` service).

```
INFO  [alembic.runtime.migration] Running upgrade 003_tool_policies -> 004_tenant_id_varchar, Change tool_policies.tenant_id and audit_logs.tenant_id to VARCHAR(255),
matching Block D's canonical tenants.tenant_id type.
```

Exit code 0.

```
SELECT version_num FROM alembic_version;
```

```
      version_num
-----------------------
 004_tenant_id_varchar
```

```
docker exec snyq_postgres psql -U postgres -d control_plane -c "\d tool_policies"
```

```
                      Table "public.tool_policies"
   Column    |           Type           | Collation | Nullable | Default
-------------+--------------------------+-----------+----------+---------
 id          | uuid                     |           | not null |
 tenant_id   | character varying(255)   |           | not null |
 server_name | character varying(64)    |           | not null |
 tool_name   | character varying(128)   |           | not null |
 allowed     | boolean                  |           | not null |
 created_at  | timestamp with time zone |           | not null | now()
 updated_at  | timestamp with time zone |           | not null | now()
Indexes:
    "tool_policies_pkey" PRIMARY KEY, btree (id)
    "ix_tool_policies_tenant_id" btree (tenant_id)
    "ix_tool_policies_tenant_id_server_name" btree (tenant_id, server_name)
    "uq_tool_policies_tenant_server_tool" UNIQUE CONSTRAINT, btree (tenant_id, server_name, tool_name)
```

```
docker exec snyq_postgres psql -U postgres -d control_plane -c "\d audit_logs"
```

```
                        Table "public.audit_logs"
   Column    |           Type           | Collation | Nullable | Default
-------------+--------------------------+-----------+----------+---------
 id          | uuid                     |           | not null |
 tenant_id   | character varying(255)   |           | not null |
 actor_id    | uuid                     |           | not null |
 action_type | character varying(100)   |           | not null |
 target_json | jsonb                    |           |          |
 ip_address  | character varying(64)    |           |          |
 created_at  | timestamp with time zone |           | not null | now()
Indexes:
    "audit_logs_pkey" PRIMARY KEY, btree (id)
    "ix_audit_logs_action_type" btree (action_type)
    "ix_audit_logs_actor_id" btree (actor_id)
    "ix_audit_logs_tenant_id" btree (tenant_id)
    "ix_audit_logs_tenant_id_created_at" btree (tenant_id, created_at)
```

Both `tenant_id` columns are **`character varying(255)`**, not `uuid`. Indexes still present. No extra index rebuild required.

Downgrade uses `tenant_id::uuid` and will fail loudly if non-UUID strings have been written — intended.

---

## 6.3 Model files

`.bak` taken before edit: `tool_policy.py.bak`, `audit_log.py.bak`.

| File | `tenant_id` | Unchanged UUID columns |
|------|-------------|------------------------|
| `backend/app/models/tool_policy.py` | `Mapped[str]` / `String(255)` | `id` remains `PG_UUID` |
| `backend/app/models/audit_log.py` | `Mapped[str]` / `String(255)` | `id` and **`actor_id`** remain `PG_UUID` |

`UUID` / `PG_UUID` imports kept because `id` (and `actor_id` on audit) still need them.

Named, not fixed this session: `app.services.admin.audit_logger.write_audit_log` still type-hints `tenant_id: UUID`. That is Block N call-site typing. SQLAlchemy will coerce a UUID value into VARCHAR on insert; aligning the hint is N’s follow-up, not this migration.

---

## 6.4 Test collection vs prior baseline

```
python -m pytest tests/ --collect-only -q
```

| Session | Result |
|---------|--------|
| v2 (`003_tool_policies`) | `161 tests collected, 5 errors` |
| **this session (`004`)** | **`161 tests collected, 5 errors in 3.71s`** |

Same five pre-existing collection errors: `libmagic` (`test_block_c_advanced`, `test_mime_detector`, `test_pipeline_integration`, `test_signoff_block_c`) and `TokenExpiredError` (`test_signoff.py`). Unrelated to this type change.

---

## 6.5 UUID-cast gate — closed

`BUILD_PASS_M_2026-08-17_v3.md` stopped because JWT `tenant_id` is an opaque string (Block D `VARCHAR(255)`, content APIs, `"tenant-k"`) while `tool_policies` / `audit_logs` were `uuid`.

That mismatch is gone: both tables now store `tenant_id` as `VARCHAR(255)`, matching Block D’s canonical `tenants.tenant_id`. Block M can bind the JWT claim as a string and use it at the query boundary with no UUID cast.

The next MCP gateway build prompt (§3 of “Complete MCP Gateway Integration”) can proceed **without re-running this specific UUID-cast gate**. A full Part A observe-first pass should still run fresh against the current commit, per the standing rule.

Stopped here. No Block M code, no `SIGNOFF.md` edits, no commit, no push.
