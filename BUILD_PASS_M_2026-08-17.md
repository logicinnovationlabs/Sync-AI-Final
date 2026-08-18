# Build Pass — Block M: MCP Gateway (Observe First only)

**Date:** 2026-08-17
**Type:** Observe-first. Diagnose which side is wrong. Do not build while gates are open.
**This file is not `SIGNOFF.md`.** Independent §24 rule-1 reviewer signoff is still required.

**Commit tested (HEAD):** `5ce77b1` (`5ce77b1a97f3bf0ea0ba980282940f517e7ad911`) — `Add: Block N completed and tested`
**Branch:** `Pratham`
**Repo:** `logicinnovationlabs/Sync-AI-Final`

`.env` / `backend/.env` were never opened. No commits, no pushes, no staging, no `SIGNOFF.md` edits. No Block M files created. `backend/app/services/mcp_gateway/` does not exist.

---

## 5.1 Part A — Observe-first results (raw output)

### Command 1 — current commit

```
git log -1 --oneline
```

```
5ce77b1 Add: Block N completed and tested
```

Also recorded: branch `Pratham`, full SHA `5ce77b1a97f3bf0ea0ba980282940f517e7ad911`.

---

### Command 2 — `acl_checker.py` in full

```
cat backend/app/services/document_reader/acl_checker.py
```

```
"""ACL re-check via Block C  no caching (K1)."""

from __future__ import annotations

import logging
from typing import Protocol, Set, Tuple

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class ACLChecker(Protocol):
    async def is_allowed(
        self, tenant_id: str, principal_id: str, doc_id: str
    ) -> bool: ...


class MockACLChecker:
    """Phase 1 / in-process ACL. No caching — each call reads current state."""

    def __init__(self) -> None:
        self._allowed: Set[Tuple[str, str, str]] = set()
        self.call_count: int = 0
        self._history: list[Tuple[str, str, str, bool]] = []

    def grant(self, tenant_id: str, doc_id: str, principal_id: str) -> None:
        self._allowed.add((tenant_id, doc_id, principal_id))

    def revoke(self, tenant_id: str, doc_id: str, principal_id: str) -> None:
        self._allowed.discard((tenant_id, doc_id, principal_id))

    def clear(self) -> None:
        self._allowed.clear()
        self.call_count = 0
        self._history.clear()

    async def is_allowed(
        self, tenant_id: str, principal_id: str, doc_id: str
    ) -> bool:
        self.call_count += 1
        allowed = (tenant_id, doc_id, principal_id) in self._allowed
        self._history.append((tenant_id, principal_id, doc_id, allowed))
        return allowed


class HttpACLChecker:
    """Phase 2 — call Block C /acl/compile with no local cache."""

    def __init__(self, acl_service_url: str, timeout: float = 5.0) -> None:
        self.acl_service_url = acl_service_url.rstrip("/")
        self.timeout = timeout

    async def is_allowed(
        self, tenant_id: str, principal_id: str, doc_id: str
    ) -> bool:
        url = f"{self.acl_service_url}/acl/compile"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    url,
                    json={
                        "tenant_id": tenant_id,
                        "principal_id": principal_id,
                        "document_id": doc_id,
                    },
                )
        except httpx.HTTPError as exc:
            logger.error("ACL service unreachable: %s", exc)
            raise HTTPException(status_code=500, detail="ACL service unavailable") from exc

        if resp.status_code != 200:
            logger.error("ACL service status=%s body=%s", resp.status_code, resp.text)
            raise HTTPException(status_code=500, detail="ACL service unavailable")

        data = resp.json()
        if "allowed" in data:
            return bool(data["allowed"])
        if "decision" in data:
            return str(data["decision"]).lower() in {"allow", "allowed", "permit"}
        if "access" in data:
            return str(data["access"]).lower() in {"allow", "allowed", "permit"}
        return False


async def check_acl(
    checker: ACLChecker,
    tenant_id: str,
    principal_id: str,
    doc_id: str,
) -> bool:
    """Re-evaluate access on every call — never cache (K1)."""
    return await checker.is_allowed(tenant_id, principal_id, doc_id)


def create_acl_checker(settings) -> MockACLChecker | HttpACLChecker:
    if settings.acl_backend == "http":
        return HttpACLChecker(settings.acl_service_url)
    return MockACLChecker()
```

**Does it call `app/acl/`?** No. Zero imports of `app.acl`, `ACLCompiler`, or `app.api.v1.acl`.

**Does it have its own allow/deny logic?** Yes.

- `MockACLChecker` keeps a private `_allowed: Set[Tuple[str, str, str]]` and decides allow/deny from membership of that set (`grant` / `revoke` / `is_allowed`). That is a second ACL store and a second decision function.
- `HttpACLChecker` POSTs to `{acl_service_url}/acl/compile` over HTTP and locally interprets `allowed` / `decision` / `access`. It does not import Block C.
- `backend/app/api/v1/acl.py` currently exposes only `GET /acl/{document_id}` (UUID `tenant_id` query). There is no `/acl/compile` route in that file. Repo-wide, the only `/acl/compile` string is this checker. The Phase-2 path is not wired to the real compiler.

Canonical ACL remains `backend/app/acl/` (`ACLCompiler` with “Apply deny overrides” in `compiler.py`). `document_reader/reader.py` and `api/v1/document.py` call `acl_checker.is_allowed`, not `app.acl`.

**Gate (2): FIRED.** Live defect, same class as the F/G/H second-ACL copy. Block M must not be built on top of this surface.

---

### Command 3 — ACL / jwt_auth files (tests and `__pycache__` excluded)

```
find backend -iname "*acl*" -o -iname "*jwt_auth*" | grep -v test | grep -v __pycache__
```

```
backend/app/acl
backend/app/api/v1/acl.py
backend/app/services/document_reader/acl_checker.py
```

No `jwt_auth` file. Auth is one implementation: `backend/app/api/deps.py` (`get_current_user` → `token_service.validate_token`). Content APIs import that; they do not ship a second verifier.

ACL is **not** one implementation: `app/acl` (compiler) plus `document_reader/acl_checker.py` (independent allow-set / HTTP client). `api/v1/acl.py` is a debug GET over `CanonicalRepo`, not a third compiler, but it is a second HTTP ACL surface.

---

### Command 4 — how content APIs bind `tenant_id`

```
grep -n "tenant_id" backend/app/api/v1/search/lexical.py
```

```
33:    tenant_id: str = Field(..., description="Tenant identifier")
77:    """Extract tenant_id from authenticated user."""
78:    tenant_id = current_user.get("tenant_id")
79:    if not tenant_id:
80:        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")
81:    return tenant_id
88:    tenant_id: str = Depends(get_tenant),
101:    if request.tenant_id != tenant_id:
107:            f"ACL empty for user={request.user_id} tenant={request.tenant_id} — fail-closed"
117:            tenant_id=request.tenant_id,
133:            f"Performance outlier: took_ms={took_ms:.2f} tenant={request.tenant_id} query_len={len(request.query)}"
165:    tenant_id: str = Depends(get_tenant),
174:    logger.info(f"Triggered indexing for {len(document_ids)} documents in tenant {tenant_id}")
```

```
grep -n "tenant_id" backend/app/api/v1/search/vector.py
```

```
25:    tenant_id: str = Field(..., description="Tenant identifier")
62:    """Extract tenant_id from authenticated user."""
63:    tenant_id = current_user.get("tenant_id")
64:    if not tenant_id:
65:        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")
66:    return tenant_id
73:    tenant_id: str = Depends(get_tenant),
87:    if request.tenant_id != tenant_id:
101:            f"ACL empty for user={request.user_id} tenant={request.tenant_id} — fail-closed"
109:            tenant_id=request.tenant_id,
124:            f"Performance outlier: took_ms={took_ms:.2f} tenant={request.tenant_id} top_k={request.top_k}"
153:    tenant_id: str = Depends(get_tenant),
168:        count = await store.upsert_batch(tenant_id=tenant_id, chunks=chunks)
173:    logger.info(f"Ingested {count} vectors for tenant {tenant_id}")
177:        "tenant_id": tenant_id,
```

```
grep -n "tenant_id" backend/app/api/v1/document.py
```

```
36:# Block K is a content API keyed by the JWT tenant_id string (same pattern as
57:    """Return the JWT tenant_id as a string store key.
60:    ``UUID(tenant_id)`` against a PG_UUID column. The document store (and
61:    Block D's VARCHAR tenant_id schema) keys by opaque string. Passing the
65:    tenant_id = current_user.get("tenant_id")
66:    if not tenant_id:
67:        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")
68:    return str(tenant_id)
93:    tenant_id: str = Depends(get_document_tenant),
113:    metadata = await store.get_metadata(tenant_id, doc_id)
118:    allowed = await acl_checker.is_allowed(tenant_id, principal_id, doc_id)
127:    structured_data = await store.get_structured_metadata(tenant_id, doc_id)
137:                tenant_id,
153:        tenant_id=tenant_id,
```

**Pattern to copy when M is unblocked:** JWT claim as `str` via a local `get_tenant` / `get_document_tenant`. Do **not** use `deps.get_tenant` (control-plane `UUID(tenant_id)` routing). Lexical and vector already do this; document.py documents why.

---

### Command 5 — `tool_policies`

```
grep -rn "tool_policies" backend/app/models/ backend/migrations/ services/block-d-storage/migrations/ 2>/dev/null
```

*(empty — no lines)*

Those three directories exist (`ls -d` listed all three). Repo-wide search for `tool_policies` also returned **no matches**.

**Gate (5): FIRED.** Schema gap in Block D/C. Block M must not invent an allowlist store.

Draft only (not applied, not added to this repo this session). Same shape as §9.2 `acl_entries` / `oauth_clients`:

```sql
CREATE TABLE tool_policies (
    id              UUID PRIMARY KEY,
    tenant_id       VARCHAR(255) NOT NULL,
    server_name     VARCHAR(64)  NOT NULL,
    tool_name       VARCHAR(128) NOT NULL,
    allowed         BOOLEAN      NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, server_name, tool_name)
);
```

Writer: Block N only. Reader: Block M. This session did not create a model or migration.

---

### Command 6 — revocation publish / `session.revoked`

```
grep -n "revoke\|publish\|emit\|produce" backend/app/services/token_service.py
```

```
188:            RevokedTokenError if token has been revoked (A2).
218:            revoked = await redis_client.sismember(tenant_id, f"revoked:{jti}", jti)
219:            if revoked:
222:        # Block N: principal-level session revoke via token_version (Redis,
```

```
grep -rn "session.revoked\|revoked.v1" backend/app/ 2>/dev/null
```

```
backend/app/api/v1/admin/sessions.py:92:        action_type="session.revoked",
backend/app/services/revocation.py:113:            "event_type": "session_revoked",
```

(`__pycache__` binary hits omitted.)

**Gate (6): did not fire as empty.** Block A already publishes.

Evidence from `backend/app/services/revocation.py`:

- `revoke_token` publishes Redis pub/sub `revocation_events` with `event_type: "token_revoked"` (jti + tenant_id).
- `revoke_session` publishes the same channel with `event_type: "session_revoked"` (principal_id + tenant_id).
- `token_service.validate_token` rejects on Redis `revoked:{jti}` and on `token_version` bump (Block N admin revoke).
- `admin/sessions.py` calls `revocation_service.revoke_session` and writes an **audit** row `action_type="session.revoked"`.

Not architecture-literal `session.revoked.v1` on Redpanda. Mechanism present: Redis channel `revocation_events` plus per-request Redis checks inside `validate_token`. When M is unblocked, M4 is a subscriber to that channel (plus the 30–60 min cache ceiling), not a new Block A publish and not per-call `/oauth/introspect` polling.

---

### Command 7 — shared audit table

```
grep -rn "audit_log\|admin_audit" backend/app/models/ backend/migrations/ 2>/dev/null
```

```
backend/app/models/audit_log.py:20:    __tablename__ = "audit_logs"
backend/app/models/audit_log.py:22:        Index("ix_audit_logs_tenant_id_created_at", "tenant_id", "created_at"),
backend/migrations/env.py:21:from app.models.audit_log import AuditLog  # noqa: F401 — Block N metadata
backend/migrations/versions/002_block_n_admin.py:72:        "audit_logs",
backend/migrations/versions/002_block_n_admin.py:86:    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
backend/migrations/versions/002_block_n_admin.py:87:    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
backend/migrations/versions/002_block_n_admin.py:88:    op.create_index("ix_audit_logs_action_type", "audit_logs", ["action_type"])
backend/migrations/versions/002_block_n_admin.py:90:        "ix_audit_logs_tenant_id_created_at",
backend/migrations/versions/002_block_n_admin.py:91:        "audit_logs",
backend/migrations/versions/002_block_n_admin.py:97:    op.drop_index("ix_audit_logs_tenant_id_created_at", table_name="audit_logs")
backend/migrations/versions/002_block_n_admin.py:98:    op.drop_index("ix_audit_logs_action_type", table_name="audit_logs")
backend/migrations/versions/002_block_n_admin.py:99:    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
backend/migrations/versions/002_block_n_admin.py:100:    op.drop_index("ix_audit_logs_tenant_id", table_name="audit_logs")
backend/migrations/versions/002_block_n_admin.py:101:    op.drop_table("audit_logs")
```

**Gate (7): did not fire as empty.** Block N already defined `audit_logs`.

Columns (`backend/app/models/audit_log.py` + migration `002_block_n_admin.py`): `id`, `tenant_id` (PG UUID), `actor_id` (PG UUID, comment: admin principal), `action_type`, `target_json` (JSONB), `ip_address`, `created_at`.

M3 wants host, client, user, tool, outcome as first-class facts. They are not columns. They could be stuffed into `action_type` + `target_json`, but `tenant_id`/`actor_id` are UUID-only while content APIs (and M, when built) bind string JWT `tenant_id`. That is a shared M/N mapping question, not a missing table. Not inventing a second audit table this session.

---

### Command 8 — import-linter config

```
cat importlinter-config.ini 2>/dev/null
```

*(empty — file does not exist at repo root)*

Repo-wide find for `*importlinter*` / `importlinter-config.ini`: no files. No `importlinter` / `import-linter` strings in the repo. The MCP contracts from the architecture prompt are not present because the config file itself is not present.

Not a Part A stop-gate. When M is unblocked, the file has to be created, not merely appended.

---

## 5.2 Gates — which fired, what is blocking

| Gate | Fired? | Verdict |
|------|--------|---------|
| (2) `acl_checker.py` own allow/deny | **YES** | Live second-ACL defect. Stop. |
| (5) `tool_policies` missing | **YES** | Block D/C schema gap. Stop. Do not invent a table in M. |
| (6) revocation event missing | **NO** | Redis `revocation_events` + `validate_token` Redis checks exist. Name is `session_revoked`, not `session.revoked.v1`. |
| (7) audit table missing | **NO** | `audit_logs` exists from Block N. Field/UUID mapping still needs M/N agreement before M writes rows. |

**Build did not start.** Part B was not entered.

### What is blocking, exactly

1. **Block K / document reader — second ACL (do not fix in this Block M session).** `acl_checker.py` is not a thin wrapper over `app/acl/`. `MockACLChecker` is an in-process allow-set. `HttpACLChecker` calls a `/acl/compile` HTTP path that is not implemented on `api/v1/acl.py`. Full-document reads from a future MCP gateway would go through this checker. Building M on it would repeat the F/G/H consolidation defect.

2. **Block D/C — no `tool_policies` table.** M2 (allowlist) has nothing to read. Draft SQL is in §5.1 command 5. Owner of the write path is Block N; owner of the schema is D/C. Not M.

Until both are closed, M1–M4 cannot be run honestly. Identity binding (M1) could be sketched against JWT string binding, but allowlist (M2) has no store, and routing document reads through K inherits the second ACL.

### Named, not fixed (F–L / N)

- `document_reader/acl_checker.py` second ACL — Block K.
- No `/acl/compile` route despite `HttpACLChecker` targeting it — Block C/K.
- `audit_logs.tenant_id` is PG UUID; content APIs use string JWT `tenant_id` — same dual contract as K’s 500, now on N’s audit table.
- `importlinter-config.ini` absent repo-wide.

---

## 5.3 What was built

Nothing. No `backend/app/services/mcp_gateway/`. No router in `main.py`. No `.bak` files (no edits). No import-linter file created (would be Part B).

When gates clear, copy:

- Tenant: `current_user.get("tenant_id")` as `str` (lexical / vector / `get_document_tenant`).
- Auth: `Depends` on `app.api.deps` / `token_service.validate_token`. No second JWT verifier.
- ACL: `app.acl` only, after K’s checker is reduced to a wrapper or removed.
- Allowlist: read-only `tool_policies`.
- Audit: existing `audit_logs` after M/N agree how host/client/user/tool/outcome map.
- Revocation: subscribe to Redis `revocation_events`; keep 30–60 min cache ceiling; do not poll introspect.

---

## 5.4 M1–M4

Not run. No gateway to test. Not labeled Phase 1 or Phase 2.

| ID | Criterion | This session |
|----|-----------|--------------|
| M1 | Identity binding | **NOT RUN** — no module |
| M2 | Allowlist enforcement | **NOT RUN** — no `tool_policies` |
| M3 | Audit completeness | **NOT RUN** — no module; table exists |
| M4 | Session propagation ≤60s | **NOT RUN** — no module; Redis event exists for a future subscriber |

---

## 5.5 Updated overall D–M status

D–L from prior passes (`BUILD_PASS_K-L_2026-08-16.md`), not re-run this session.

| Block | Phase 1 (mock) | Phase 2 (real infra) | Notes |
|-------|----------------|----------------------|--------|
| D Storage | PASS (prior) | **PASS** (prior) | No `tool_policies` in models or migrations (this session) |
| E Chunking | PASS (prior) | **PASS** (prior) | |
| F Lexical | PASS (prior) | **PASS** (prior) | JWT `tenant_id` as string |
| G Vector | PASS (prior) | **PASS** (prior) | JWT `tenant_id` as string |
| H Graph | PASS (prior) | **PASS** (prior) | |
| I Signals | PASS (prior) | **PASS** (prior) | |
| J Federator | PASS (prior) | **PASS** (prior) | |
| K Reader | **PASS** (prior, 7/7 signoff) | **Not reached** | JWT string tenant. **Live:** `acl_checker.py` is a second ACL, not `app/acl` |
| L Orchestrator | Architecture L1–L4 PASS (prior) | Live OpenRouter (prior) | |
| N Admin | Commit message says completed | Not re-verified here | `audit_logs` exists; no `tool_policies` writer possible until the table exists |
| Q (K+L) | PASS (prior report) | Pending independent reviewer | Not written to `SIGNOFF.md` |
| **M Gateway** | **BLOCKED** | **BLOCKED** | Observe-first only. Gates (2) and (5) open |

**Bottom line:** Block M was not built. `acl_checker.py` is a live second ACL. `tool_policies` does not exist. Revocation publish (Redis) and `audit_logs` do exist. Close those two gates, then build M as a module in the existing app with JWT-string tenant binding.

Stopped here. No `SIGNOFF.md` edits, no N/O work, no commit, no push.
