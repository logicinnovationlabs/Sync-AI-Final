# Frontend Integration — suhani UI against unified Pratham backend

**Date:** 2026-08-17  
**Branch:** `frontend-integration` (off Pratham `5ce77b1`; **not** merged to Pratham)  
**Part A:** `FRONTEND_AUDIT.md` (commit `20be522`)  
**This file is Part B.** Not a signoff. PASS only where a real HTTP round-trip was captured.

Architecture PDF and `00-SHARED-CONTRACTS.md` remain absent from the tree (see Part A §0). Live FastAPI routes + `contracts/*.yaml` path lists were used as the contract surface.

---

## B1. Single backend base URL

| Item | Result |
|------|--------|
| Env var | `NEXT_PUBLIC_API_BASE_URL` (already in `frontend/lib/api/client.ts`) |
| Default | `http://localhost:8000/api/v1` — matches `docker-compose.yml` service `app` host port **8000** |
| Per-block ports | None found; none introduced |
| Fresh clone | `frontend/.env.example` added; `frontend/.gitignore` now un-ignores `.env.example` |

`.env.example`:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_DEFAULT_TENANT=alpha
NEXT_PUBLIC_SITE_URL=http://localhost:3000
```

The `/api/v1` suffix is required. Frontend paths are `/auth/login`, `/me`, `/search/federated`, etc.

---

## B2. Auth flow against Block A (real HTTP)

Uvicorn was started on this machine as the real FastAPI app (`app.main:app`) on `127.0.0.1:8000`. `snyq_app` Docker container does **not** exist. Infra used: `snyq_postgres` (`:5432`), Redis on `:6379`. JWT PEM files were **missing**; `TokenService` generates ephemeral RS256 keys in-process for development (tokens do not survive process restart).

### Captured: GET /health

```
GET http://127.0.0.1:8000/health
status 200
{"status":"healthy","timestamp":"2026-08-17T13:26:32.520682Z","environment":"development"}
```

### Captured: POST /api/v1/auth/login (seed credentials from `seed_tenants.py`)

```
POST http://127.0.0.1:8000/api/v1/auth/login
body: {"email":"admin@alpha.test","password":"(redacted)","tenant_subdomain":"alpha"}
status 422
{
  "detail": [{
    "type": "value_error",
    "loc": ["body", "email"],
    "msg": "value is not a valid email address: The part after the @-sign is a special-use or reserved name that cannot be used with email.",
    "input": "admin@alpha.test"
  }]
}
```

**B2 login: FAIL.** Two independent facts, both captured:

1. Pydantic `EmailStr` on `NativeLoginRequest` rejects `.test` (current `email-validator` reserved-name rule). Seed script emails are `admin@alpha.test` / `member@alpha.test`.
2. `control_plane.tenants` and `control_plane.users` are **empty** (0 rows). There is no loginable principal in this Postgres even if the TLD were accepted.

GET `/me` and Bearer attachment were **not** proven with a Block A–issued token. Frontend code path is: login → `getMe(access_token)` → store only if `/me` succeeds → `Authorization: Bearer` on later calls. That matches Block A middleware (`HTTPBearer`). It was not executed end-to-end because login never returned a token.

A follow-up `POST /admin/tenants` (EmailStr-valid `admin@logicinnovationlabs.com`, new DB `frontend_smoke`) returned **500** with the standard error envelope. Server log: asyncpg `WinError 121` semaphore timeout on SSL connect to the tenant DB. **Not patched** (backend-out-of-scope).

**Not papered over:** EmailStr was not relaxed. No frontend shim accepts `.test` by rewriting the address. No Block A code was changed. Owner of the seed/EmailStr clash: **backend Block A + seed_tenants.py** (out of scope for this frontend pass).

SSO: both sides still stub (`GET /auth/sso/callback` does not issue a session; frontend `/sso/callback` is a static notice). Refresh grant remains **501**. Frontend still does not implement a refresh dance (would not work). Flagged, not shimmmed.

---

## B3. Per-page PASS/FAIL

Binary rule: PASS only with a captured real request/response that is correctly shaped and rendered without guessing.

| Page | Wired to | Round-trip evidence | Status |
|------|----------|---------------------|--------|
| Marketing `/`, `/pricing`, `/privacy`, `/terms` | None (static) | N/A — no backend call by design | **N/A** (not PASS) |
| `/login` | `POST /api/v1/auth/login` then `GET /api/v1/me` | Login captured **422** (see B2). `/me` not reached. | **FAIL** |
| `/register` | No POST (blocked — contract mismatch) | Intentionally does not call `POST /admin/users` with the suhani body. Unauthenticated call would not match Block N invite. | **blocked** (not integrated) |
| `/sso/callback` | None | Static notice. Block A callback is a stub. | **blocked** |
| `/chat` | `POST /api/v1/assistant/orchestrator/chat` (NDJSON) | Not reached — no Bearer token. | **FAIL** (wired, no authenticated round-trip) |
| `/documents` | `POST /api/v1/search/federated`; `GET /api/v1/document/{id}` | Not reached — no Bearer token. | **FAIL** (wired, no authenticated round-trip) |
| `/documents` upload | No ingest API | Files stay `queued` in the browser; copy says so. | **blocked** |
| `/connectors` | GET/POST connector status, backfill, disconnect, Google authorize | Not reached — no Bearer token. Member JWTs also lack `connectors.read/write` (audit A3.5). | **FAIL** (wired, no authenticated round-trip) |
| `/admin` | `GET /api/v1/admin/users`, `GET /api/v1/admin/audit` | Not reached — no Bearer token. | **FAIL** (wired, no authenticated round-trip) |
| `/settings/account` | `GET /api/v1/me`, `POST /api/v1/me/change-password` | `/me` not reached. | **FAIL** (wired, no authenticated round-trip) |
| `/dev/theme` | None | N/A | **N/A** |

Smoke driver: `frontend/scripts/smoke-real-backend.mjs` (same paths as `frontend/lib/api/*`).

Second run (health still 200) also captured:

```
POST http://127.0.0.1:8000/admin/tenants
body: subdomain=fesmoke, db_name=frontend_smoke, admin_email=admin@logicinnovationlabs.com
status 500
{
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "message": "An unexpected error occurred"
  },
  "timestamp": "2026-08-17T13:33:08.293229Z"
}
```

Uvicorn traceback (not patched): `asyncpg` `OSError: [WinError 121] The semaphore timeout period has expired` while connecting to the tenant database (`_create_ssl_connection`). Frontend did not change Block N. Node then aborted with `UV_HANDLE_CLOSING` (exit `-1073740791`) after printing the summary.

---

## B4. Blocked features (not faked)

| Feature | Why blocked |
|---------|-------------|
| Self-serve register | Block N invite is `require_admin` + generated password. Suhani posted unauthenticated `{tenant_subdomain,email,password,display_name}`. Frontend no longer sends that payload. |
| Google / OIDC sign-in | Block A `sso_callback` does not issue a session. Button remains a notice. |
| Refresh-token dance | `POST /oauth/token` `refresh_token` grant is **501**. Frontend stores `refresh_token` and does not send it. |
| Browser file ingest | No user-upload ingest route on the unified backend. Upload widget stays queued. |
| Outlook / WhatsApp / Tally connectors | `available: false` in `lib/connectors.ts`; no backend integration. |
| Block O traces/metrics UI | No FastAPI `/traces` or `/metrics` on `app`. Frontend has no observability pages. |
| Block M MCP UI | Frontend never called MCP. Module exists (`GET/POST /mcp/{server}`); not a product page. Not stubbed. |

---

## Contract mismatches (resolved vs open)

| Mismatch | Resolution | Owner |
|----------|------------|--------|
| Chat/documents were demo-only; J/K/L exist on Pratham | Frontend now calls live paths: `/assistant/orchestrator/chat`, `/search/federated`, `/document/{id}` | frontend (this pass) — **unverified at runtime** without a token |
| `contracts/assistant-contract.yaml` `/api/v1/assistant/chat` vs live `/assistant/orchestrator/chat` | Frontend uses the **live** path | open on contracts yaml |
| `contracts/query-contract.yaml` `/api/v1/search` vs live `/search/federated` | Frontend uses live path | open on contracts yaml |
| `contracts/reader-contract.yaml` `POST /api/v1/read` vs live `GET /document/{id}` | Frontend uses live GET | open on contracts yaml |
| Register body vs Block N invite | **Left open.** Frontend stopped calling the wrong shape. No shim. | Block N / product (self-serve vs invite) |
| Seed emails `@alpha.test` vs `EmailStr` | **Left open.** Not patched. Captured 422. | Block A `NativeLoginRequest` + `seed_tenants.py` |
| Login response extra `role` / `must_change_password` | Frontend types accept them as optional | closed |
| `/me` extra `role` / `must_change_password` | Frontend `MeResponse` updated | closed |
| Member scopes vs connector APIs | Documented; not widened from the frontend | Block A `scopes_for_role("member")` |
| Error envelope `detail` vs `{error:{message}}` | `formatApiError` handles both, including 422 arrays | closed on frontend |
| JWT keys missing on disk | Dev generator in `token_service`; not a frontend fix | backend local setup |

---

## Files changed (Part B) and why

| Path | Why |
|------|-----|
| `frontend/.env.example` | One-value pointer at unified backend + localhost tenant |
| `frontend/.gitignore` | Allow committing `.env.example` |
| `frontend/lib/api/client.ts` | Parse FastAPI `detail` arrays and error envelope |
| `frontend/lib/api/auth.ts` | Login extras; remove self-serve `register()` client |
| `frontend/lib/api/assistant.ts` | Block L NDJSON stream client |
| `frontend/lib/api/search.ts` | Block J federated search + Block K GET document |
| `frontend/lib/api/admin.ts` | Block N users + audit |
| `frontend/lib/auth/jwt.ts` | Optional `role` / `must_change_password` claims |
| `frontend/components/auth/login-form.tsx` | Require tenant; prove token via `GET /me` before storing session |
| `frontend/components/auth/register-form.tsx` | Honest blocked copy; no mismatched POST |
| `frontend/app/(auth)/register/page.tsx` | Copy matches invite-only contract |
| `frontend/components/chat/chat-view.tsx` | Live Block L instead of `DEMO_ANSWERS` |
| `frontend/components/chat/source-card.tsx` | Citations without requiring demo connector types |
| `frontend/components/documents/document-browser.tsx` | Live J search + K read; upload still honest |
| `frontend/components/admin/admin-console.tsx` | Live N users/audit |
| `frontend/app/(app)/admin/page.tsx` | Mount console |
| `frontend/components/settings/account-settings.tsx` | Live `/me` + change-password |
| `frontend/app/(app)/settings/account/page.tsx` | Mount settings |
| `frontend/scripts/smoke-real-backend.mjs` | Same-path HTTP evidence harness |
| `FRONTEND_INTEGRATION.md` | This report |

No `backend/` or `services/` files were modified in Part B.

---

## Exact steps to run locally

Prerequisites: Docker Desktop; `snyq_postgres` healthy on `:5432`; Redis on `:6379`; Node 20.9+; Python 3.12+ with backend deps.

1. **Backend (unified app, one port):**

```powershell
cd backend
# copy .env.example → .env if needed; do not commit it
# generate keys if missing: python scripts/generate_keys.py
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Confirm: `GET http://127.0.0.1:8000/health` → 200.

2. **Tenant + admin that EmailStr will accept** (seed `@alpha.test` will 422 until Block A/seed is fixed):

```powershell
docker exec snyq_postgres psql -U postgres -c "CREATE DATABASE frontend_smoke;"
# then POST http://127.0.0.1:8000/admin/tenants with EmailStr-valid admin_email
# (see frontend/scripts/smoke-real-backend.mjs bootstrap body)
```

Set `NEXT_PUBLIC_DEFAULT_TENANT` to that subdomain (example: `fesmoke`).

3. **Frontend:**

```powershell
cd frontend
copy .env.example .env.local
# edit NEXT_PUBLIC_DEFAULT_TENANT to the bootstrapped subdomain
npm install
npm run dev
```

Open `http://localhost:3000/login`. Sign in with the bootstrap admin email and temporary password from `POST /admin/tenants`.

4. **Same-path smoke (no browser):**

```powershell
cd frontend
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000/api/v1"
node scripts/smoke-real-backend.mjs
```

---

## What not to do

- Do not merge `frontend-integration` into `Pratham` or `main` without review.
- Do not copy `suhani`’s `backend/` over Pratham.
- Do not treat marketing demo answers as product chat.
- Do not mark login PASS while EmailStr rejects seed users or `tenants`/`users` are empty.
- Do not build Block M or Block O to unblock UI — nothing in this frontend is waiting on them.
