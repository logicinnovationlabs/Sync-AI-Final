# Frontend Audit — suhani against unified backend (Pratham)

**Date:** 2026-08-17  
**Type:** Part A only. Inventory and contract mapping. No integration changes in this file's commit.  
**This file is not a signoff.**

| Field | Value |
|-------|--------|
| Repo | `logicinnovationlabs/Sync-AI-Final` |
| Backend target branch | `Pratham` (`origin/Pratham`) |
| Frontend source branch | `suhani` (`origin/suhani`) |
| Working branch for this pull | `frontend-integration` (created off Pratham HEAD; **not** merged into Pratham) |
| Pratham HEAD | `5ce77b1` — `Add: Block N completed and tested` |
| suhani HEAD | `5a4775c` — `feat: added frontend and ui components for synq ai` |
| Merge-base (`HEAD` ∩ `origin/suhani`) | `cdd623f` — `Initial commit: Add backend folder` |
| Frontend path (confirmed, not assumed) | `frontend/` |

---

## 0. Context documents actually loaded

The prompt required four sources, in order. This is what was actually present.

| Required source | Present in this tree? | What was used instead |
|-----------------|----------------------|------------------------|
| `Glean Arch made by Glean v1.3.1.md` (or uploaded PDF), especially §5, §18.1, §14.4, §29 | **No.** Same finding as `VERIFICATION_PASS_D-J_2026-08-16.md`, `VERIFICATION_PASS_K-L_2026-08-16.md`, `VERIFICATION_PASS_N_2026-08-17.md`, and `backend/app/services/mcp_gateway/SIGNOFF.md`. Searched repo, Desktop, Downloads, and `D:\PROJECTS`. | Live `backend/app/main.py` router mounts; `backend/app/services/token_service.py` JWT claims + §14.4 kid rotation comments; `docker-compose.yml` single `app` on `:8000`; prior session quotes of §29 (one deployable, modules not services). |
| `00-SHARED-CONTRACTS.md` in Implementation Blocks | **No.** No `Implementation Blocks/` directory. | Repo `contracts/*.yaml` (thin OpenAPI path lists, almost no field schemas) **plus the live FastAPI models** as the actual contract surface. |
| SIGNOFF.md under `/services/` (or post-consolidation equivalents) | Partial. | See §0.1 below. |

### 0.1 Block reality used for this audit

Prompt claim: D–L and N have real-infra PASS; M and O are not fully built. **Recorded against the tree, not assumed from the prompt.**

| Block | What exists on Pratham | Signoff / verification evidence in-tree | Frontend-relevant? |
|-------|------------------------|------------------------------------------|--------------------|
| A Identity / auth | `backend/app/api/v1/auth.py`, `oauth.py`, `me.py` | Core platform; JWT RS256 | **Yes** — login, token, `/me` |
| B Connectors | `backend/app/api/v1/connectors.py` | Present | **Yes** — Google Drive/Gmail |
| C Identity/ACL | `/api/v1/resolve`, `/api/v1/{document_id}` ACL | Present | No frontend caller |
| D Storage | `services/block-d-storage/SIGNOFF.md` D1–D4 **PASS** | PASS | Indirect (K reads storage) |
| E Chunking | `services/block-e-chunking/SIGNOFF.md` | PASS (prior D–J pass) | No frontend caller |
| F Lexical | `services/block-f-lexical-search/SIGNOFF.md` | PASS | Indirect via J |
| G Vector | `services/block-g-vector-search/SIGNOFF.md` | PASS | Indirect via J |
| H Graph | `services/block-h-graph/SIGNOFF.md` | PASS | No frontend caller |
| I Signals | `services/block-i-signals/SIGNOFF.md` | PASS | No frontend caller |
| J Federator | `services/block-j-query-federator/SIGNOFF.md` J1–J4 **PASS**; mounted `POST /api/v1/search/federated` | PASS | **Would be** search/documents — frontend does not call it |
| K Document reader | `GET /api/v1/document/{doc_id}` | K verification reports exist; Phase 2 wiring is a named caveat in `VERIFICATION_PASS_K-Phase2_2026-08-17.md` | **Would be** document view — frontend does not call it |
| L Assistant | `POST /api/v1/assistant/orchestrator/chat` (NDJSON stream) | K/L verification reports | **Would be** chat — frontend does not call it |
| M MCP Gateway | `GET/POST /mcp/{server}` mounted in `main.py`; `backend/app/services/mcp_gateway/SIGNOFF.md` independent review **PASS** (M1–M4) | Prompt said “not fully built”; **the tree now has a PASS SIGNOFF**. Frontend still does not call MCP. | Not called |
| N Admin | `/api/v1/admin/users`, `/connectors`, `/audit`, `/sessions`; `POST /admin/tenants` bootstrap | `VERIFICATION_PASS_N_2026-08-17.md` then `FIX_PASS_N_2026-08-17.md` | Admin page is a stub; register **does** call `/admin/users` |
| O Observability | `otel-collector` in compose; **no** FastAPI `/traces` or `/metrics` on `app`. `tests/test_blocks/test_block_o.py` is marked `provisional` and hits a mock `block_client`. | **Not a product API.** | Not called |

Unified backend topology (§29.5 as implemented): one FastAPI process, `docker-compose.yml` service `app`, host port **8000**. Frontend/admin is a separate Next.js deployable.

---

## A1. Isolation (what was pulled, what was not)

### Git operations (this session)

```
git fetch origin                          # succeeded
git checkout -b frontend-integration      # off Pratham HEAD 5ce77b1
git checkout origin/suhani -- frontend    # frontend-only pathspec
```

No wholesale merge of `suhani`. No `backend/` pathspec from `suhani`.

### suhani vs merge-base

`suhani` is **two commits** total: `cdd623f` (shared initial backend) then `5a4775c` (frontend + an older backend snapshot). Comparing `suhani` to Pratham is not a small delta — suhani’s `backend/` is a **divergent older copy** (Block A/B era), not a patch on current Pratham.

### Path classification on `suhani` (`5a4775c` tree)

**Frontend — pulled onto `frontend-integration`:**

- Entire `frontend/` (153 files, +28,492 lines vs Pratham HEAD). Confirmed directory name is `frontend/`. There is no `admin/` or `web/` app.

**Backend / other — flagged, left untouched on Pratham:**

suhani also contains a full `backend/` tree (FastAPI app, docker-compose, migrations, tests). That backend mounts only auth, oauth, me, admin, connectors, and Google webhooks — the exact topology the frontend comments describe. **None of those files were checked out.** Current Pratham `backend/` is the unified A–N module tree and must stay that.

### Topology question from the prompt

> Do not assume the frontend was built against the current (v1.3.1, unified) backend topology. It may have been built earlier, against the old seven-standalone-services layout.

**Finding:** it was built against a **single FastAPI process on `localhost:8000`**, not against per-block service ports. Evidence:

- `frontend/lib/api/client.ts` has one base URL: `NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"`.
- No `localhost:8001` / `:8002` / distinct-per-block ports anywhere in `frontend/`.
- Chat and documents explicitly say `app/main.py` mounts “auth, oauth, me, admin, connectors and webhooks, and nothing else” — that is suhani’s backend, i.e. early unified A/B, **not** the seven-standalone-services layout and **not** current Pratham (which now also mounts search, document, assistant, MCP, admin console).

So: single-base-URL already, but the **assumed API surface is A/B-only**. Chat/search/documents were stubbed because those routes did not exist on suhani’s backend. They exist on Pratham now; the frontend still does not call them.

---

## A2. Inventory of `frontend/`

### A2.1 Stack (from `frontend/package.json`, not file extensions)

| Layer | Actual |
|-------|--------|
| Framework | **Next.js `16.2.12`** (App Router: `frontend/app/`). React `19.2.4`. |
| Router | Next.js file-based App Router. Route groups: `(marketing)`, `(auth)`, `(app)`. No `react-router`. |
| State | **zustand** `5.0.14` (auth session, persisted). **TanStack React Query** `5.101.4` (connector status/mutations only). |
| Forms | `react-hook-form` + `zod` + `@hookform/resolvers`. |
| UI | Tailwind CSS v4, shadcn with **Base UI** (`@base-ui/react`), `motion`, `sonner`. |
| JWT decode | `jose` `decodeJwt` — **client-side decode only, not signature verify**. |
| HTTP | Native `fetch` via `apiFetch` in `lib/api/client.ts`. **No axios. No GraphQL client.** |
| Build | `next build` / `next dev` / `next start`. `next.config.ts` is empty (no rewrites, no proxy to API). |
| Node version | **Not declared.** No `engines` field. `@types/node` is `^20`. Next 16 requires Node **20.9+**. Treat expected runtime as Node 20 LTS. |
| `.env.example` | **None** under `frontend/`. |

### A2.2 Page / route list

| Route | File | Purpose | Hits the backend? |
|-------|------|---------|-------------------|
| `/` | `app/(marketing)/page.tsx` | Marketing landing (hero, demo, sources, FAQ, CTA) | No |
| `/pricing` | `app/(marketing)/pricing/page.tsx` | Pricing table | No |
| `/privacy` | `app/(marketing)/privacy/page.tsx` | Legal | No |
| `/terms` | `app/(marketing)/terms/page.tsx` | Legal | No |
| `/login` | `app/(auth)/login/page.tsx` | Native email/password sign-in | **Yes** — `POST /auth/login` |
| `/register` | `app/(auth)/register/page.tsx` | Self-serve join-existing-tenant | **Yes** — `POST /admin/users` then `POST /auth/login` |
| `/sso/callback` | `app/(auth)/sso/callback/page.tsx` | Static “SSO isn’t wired” notice | No (does not call `/auth/sso/callback`) |
| `/chat` | `app/(app)/chat/page.tsx` | Chat UI | **No** — `DEMO_ANSWERS` script |
| `/documents` | `app/(app)/documents/page.tsx` | Document browser + upload widget | **No** — demo rows; upload stays in memory |
| `/connectors` | `app/(app)/connectors/page.tsx` | Connector cards | **Yes** — Google Drive/Gmail status, backfill, disconnect, authorize |
| `/admin` | `app/(app)/admin/page.tsx` | Admin console placeholder: “coming up.” | No |
| `/settings/account` | `app/(app)/settings/account/page.tsx` | Account settings placeholder: “coming up.” | No (`changePassword` / `getMe` exist in the client and are unused) |
| `/dev/theme` | `app/dev/theme/page.tsx` | Theme playground | No |

App chrome: `app/(app)/layout.tsx` wraps `AppShell` (sidebar: Chat, Documents, Connectors; Admin if `isAdmin()`). Optimistic cookie gate in `proxy.ts` is **commented out**.

### A2.3 Every backend call the frontend makes

All live calls go through `apiFetch` → `fetch(`${API_BASE_URL}${path}`)`.  
`API_BASE_URL` = `process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"`.  
Paths below are **relative to that prefix**. Full example: `POST http://localhost:8000/api/v1/auth/login`.

Auth header: `Authorization: Bearer <accessToken>` when `token` is passed. JSON `Content-Type: application/json`. No cookies sent to the API.

#### Implemented and called from UI

| # | Method | Frontend path | Caller | Request body (as written) | Expected 200 body (as written) |
|---|--------|---------------|--------|---------------------------|--------------------------------|
| 1 | `POST` | `/auth/login` | `login-form.tsx`, `register-form.tsx` | `{ email, password, tenant_subdomain }` | `{ access_token, refresh_token, token_type, expires_in }` |
| 2 | `POST` | `/admin/users` | `register-form.tsx` (`register()`) | `{ tenant_subdomain, email, password, display_name }` | `{ principal_id, email, display_name, tenant_id, auth_type }` |
| 3 | `GET` | `/connectors/{source}/status` | `connector-card.tsx` | none; Bearer | `{ tenant_id, source_type, cursor, watch_active, details }` `source` ∈ `google_drive` \| `google_gmail` |
| 4 | `POST` | `/connectors/{source}/backfill` | `connector-card.tsx` | `{ source_type }` | `{ status, task_id, tenant_id, source_type }` |
| 5 | `POST` | `/connectors/{source}/disconnect` | `connector-card.tsx` | none | `{ status, tenant_id, source_type }` |
| 6 | `GET` | `/connectors/google/authorize` | `connector-card.tsx` | none; Bearer | `{ authorization_url, tenant_id }` then `window.location.href = authorization_url` |

#### Implemented in `lib/api/auth.ts` but **never called** by any page/component

| # | Method | Frontend path | Typed request | Typed response |
|---|--------|---------------|---------------|----------------|
| 7 | `GET` | `/me` | Bearer | `{ principal_id, tenant_id, scopes, iat, exp }` |
| 8 | `POST` | `/me/change-password` | `{ old_password, new_password }` + Bearer | `{ message: string }` |

#### UI that looks like an API but is not

| Surface | What it actually does |
|---------|------------------------|
| Chat (`chat-view.tsx`) | Matches the prompt against `DEMO_ANSWERS`. Unscripted questions get a hard-coded “no chat backend” message. **Zero `fetch`.** |
| Documents (`document-browser.tsx`) | Client-side filter of demo citation rows. **Zero `fetch`.** |
| Document upload | Controlled `FileUpload`; items pinned to `queued`. **No POST.** |
| Google sign-in button | `useState` notice: “Google sign-in isn’t issuing sessions yet.” Does **not** call `GET /auth/sso/login`. |
| SSO callback page | Static alert. Does **not** exchange a code. |
| Admin / account settings | Placeholder copy. |
| Logout | Clears zustand + `synq_session` cookie. Does **not** call `POST /oauth/revoke`. |
| Outlook / WhatsApp / Tally connector cards | `available: false`; Connect button is a no-op (`<span>`). |

No `axios`, no GraphQL, no WebSocket client, no EventSource.

### A2.4 Hardcoded backend references

| Location | Value | Notes |
|----------|-------|-------|
| `lib/api/client.ts` | `http://localhost:8000/api/v1` | Default **unified** backend URL + `/api/v1` prefix. Matches `docker-compose.yml` `app` port 8000. |
| `app/layout.tsx` | `http://localhost:3000` | Site origin fallback for OG metadata, **not** an API. |
| `README.md` | `http://localhost:3000` | Next.js default. |

**No per-block-service ports.** Nothing like `:8001` lexical / `:8002` vector / etc.

### A2.5 Auth flow assumption

| Question | What the frontend actually does |
|----------|----------------------------------|
| Flow type | **Native email/password** via `POST /auth/login`. Not a redirect OIDC login (Google button and `/sso/callback` are inert). |
| PKCE / authorization_code | Not implemented. `POST /oauth/token` is never called. |
| Refresh-token dance | `refresh_token` is **stored** in zustand persist and **never sent**. No timer, no `/oauth/token` grant. |
| Bearer vs cookie | API uses **`Authorization: Bearer <access_token>`**. Cookie `synq_session=1` is a boolean presence flag for a (currently disabled) Next `proxy.ts` gate. **The JWT is not in a cookie.** |
| Token storage | zustand `persist` → `localStorage` key `synq-auth` (`accessToken`, `refreshToken`, `claims`, `email`). |
| `/me` | Client exists; **no page calls it.** Session identity is the JWT payload decoded with `jose.decodeJwt` plus the email captured at login. |
| JWT claims used client-side | `sub`, `tenant_id`, `scopes`, `iat`, `exp`. Not verified (no JWKS). `proxy.ts` comment: backend has no JWKS endpoint. |
| Tenant on login | `tenant_subdomain` is **not** a form field. Derived from hostname (`acme.synq.ai` → `acme`) or `NEXT_PUBLIC_DEFAULT_TENANT` on localhost. Missing fallback → backend 404 “Tenant not found”. |
| Admin detection | `scopes` contains `connectors.write` **or** any `admin.*` scope. Native member login on current backend grants only `search.read` + `document.read`, so the admin nav stays hidden unless (a) the user is a real admin JWT or (b) localStorage `synq_dev_admin_override=1` in `NODE_ENV=development`. That override is **client-only** and does not change the Bearer token. |
| Middleware | `get_current_user` on the backend is HTTP Bearer. Frontend matches that for authenticated connector calls. Login/register send no Bearer. |

Block A on Pratham still implements:

- `POST /api/v1/auth/login` — real native login, issues RS256 access + refresh JWT. Response also includes `role`, `must_change_password` (frontend type omits them; extra fields are ignored).
- `GET /api/v1/auth/sso/login` — redirect if OIDC env is set; else 500.
- `GET /api/v1/auth/sso/callback` — stub (does not issue a session).
- `POST /oauth/token` — **501** for `authorization_code`, `refresh_token`, and `client_credentials`.
- `POST /oauth/revoke` — real, requires Bearer.
- `GET /me` — real, Bearer.

§14.4 as implemented in `token_service.py`: RS256, `kid` on issue, rotation via registered public keys. Frontend does not verify signatures and does not send `kid`.

### A2.6 Env vars the frontend expects

No `frontend/.env.example`. Inferred from source:

| Variable | Where | Required? | Default |
|----------|-------|-----------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | `lib/api/client.ts` | No | `http://localhost:8000/api/v1` |
| `NEXT_PUBLIC_DEFAULT_TENANT` | `lib/auth/tenant.ts` | **Yes for localhost login** | `""` (login 404s without it) |
| `NEXT_PUBLIC_SITE_URL` | `app/layout.tsx` | No | `http://localhost:3000` |
| `NODE_ENV` | `lib/auth/dev-overrides.ts` | implicit | Next sets this |

Note: the default API base **includes `/api/v1`**. Callers pass paths like `/auth/login`, not `/api/v1/auth/login`. If someone sets `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` without the suffix, every call 404s.

---

## A3. Map frontend expectations to real backend contracts

Canonical shapes used here: live FastAPI models on Pratham + `contracts/*.yaml` path lists. `00-SHARED-CONTRACTS.md` is absent; JWT claim names below are from `token_service.issue_access_token` (`iss`, `sub`, `tenant_id`, `scopes`, `iat`, `exp`, `jti`, optional `role` / `token_version` / `must_change_password`). Error envelope in `backend/app/core/errors.py` is `{ error: { code, message, field?, meta? }, request_id?, timestamp }`. Many routes still raise FastAPI `HTTPException`, which serializes as `{ detail: ... }`. The frontend prefers `detail`, then `error.message`.

### A3.1 Calls the frontend actually makes

| Frontend call | Expected block | Real interface exists? | Shape matches contract? |
|---------------|----------------|------------------------|-------------------------|
| `POST /api/v1/auth/login` | A | **Y** — `auth.native_login` | **Mostly Y.** Request `{email, password, tenant_subdomain}` matches `NativeLoginRequest`. Response has the four fields the frontend types, **plus** `role` and `must_change_password` (safe extra). `token_type` default `"Bearer"`. |
| `POST /api/v1/admin/users` (unauthenticated self-serve, with `password` + `tenant_subdomain`) | N (was open admin on suhani) | **Y — different contract.** Now `Depends(require_admin)`. Body is `{ email, display_name, role? }`. Password is **server-generated**. Tenant comes from JWT, not body. | **N — hard mismatch.** Unauthenticated register will 401/403. Extra `password` / `tenant_subdomain` ignored; returned `temporary_password` / `role` / `must_change_password` are not in `RegisterResponse`. **Owner: frontend must not paper over this as “signup”; Block N invite is admin-only. Flag, do not shim.** |
| `GET /api/v1/connectors/{google_drive\|google_gmail}/status` | B | **Y** | **Y** — `ConnectorStatusResponse` matches. Scope `connectors.read`. Member JWT on current backend does **not** include that scope → 403 for a normal login. |
| `POST /api/v1/connectors/{source}/backfill` | B | **Y** | **Y** for response. Request body `{ source_type }` is unused (source is the path param). Scope `connectors.write` — same member-scope gap. |
| `POST /api/v1/connectors/{source}/disconnect` | B | **Y** | **Y** (`status: "disconnected"`). Scope `connectors.write`. |
| `GET /api/v1/connectors/google/authorize` | B | **Y** | **Y** `{ authorization_url, tenant_id }`. Scope `connectors.write`. Redirect URI is backend-configured (`GOOGLE_REDIRECT_URI`), not the Next origin. |

### A3.2 Client helpers that exist but are unused

| Frontend call | Expected block | Real interface exists? | Shape matches contract? |
|---------------|----------------|------------------------|-------------------------|
| `GET /api/v1/me` | A | **Y** | **Mostly Y.** Backend also returns `role`, `must_change_password`. Frontend type omits them. **Never called.** |
| `POST /api/v1/me/change-password` | A | **Y** | **Y** `{ old_password, new_password }` → `{ message }`. **Never called.** Account page is a stub. |

### A3.3 Features with no frontend HTTP call (real backends now exist)

These are **not** “blocked because M/O missing.” They are **unwired**: the UI is demo/stub, Pratham has the route.

| UI feature | Real Pratham interface | Contract notes |
|------------|------------------------|----------------|
| Chat | `POST /api/v1/assistant/orchestrator/chat` (Block L). NDJSON stream: `meta` / `token` / `final`. Body `{ prompt, session_id, tenant_id?, attachments? }`. | `contracts/assistant-contract.yaml` lists `POST /api/v1/assistant/chat` — **path mismatch vs live route** (`/assistant/orchestrator/chat`). Frontend currently calls neither. Wiring this is a Part B product decision: must consume NDJSON, not a single JSON blob. |
| Chat sessions | `GET/DELETE /api/v1/assistant/orchestrator/sessions/{session_id}` | No frontend session model. |
| Search / document list | `POST /api/v1/search/federated` (Block J). Body `{ query, tenant_id?, filters?, from, size, enable_* }`. Response `{ results[], total, took_ms, degraded, backends, query }`. | `contracts/query-contract.yaml` lists `POST /api/v1/search`. Live path is `/search/federated`. Frontend documents page filters demo rows locally. There is **no** “list all documents” API. |
| Document view | `GET /api/v1/document/{doc_id}` (Block K). ACL re-check; may stream JSON if large. | `contracts/reader-contract.yaml` lists `POST /api/v1/read`. Live is GET-by-id. Frontend has no document-id navigation. |
| Upload / ingest | None for “user dropped a PDF in the browser.” Ingest is connector backfill / embed jobs (`POST /embed`), not a browser upload. | Honest: **no matching external API**. Do not invent one in Part B. |
| Admin users / audit / session revoke | `GET/POST/PATCH/DELETE /api/v1/admin/users`, `GET /api/v1/admin/audit`, `POST /api/v1/admin/sessions/revoke` | Admin page is “coming up.” Not blocked on M/O. |
| Tenant bootstrap | `POST /admin/tenants` (no `/api/v1` prefix) | Frontend does not call it. Register assumes tenant already exists. |
| Logout revoke | `POST /oauth/revoke` | Frontend only clears local storage. |
| SSO | `GET /auth/sso/login` + callback | Callback is a stub on **both** sides. Do not fake it. |

### A3.4 Blocked — dependency not built (M / O)

Per the prompt: do not stub these in this pass; just record them.

| Would-be frontend call | Block | Status |
|------------------------|-------|--------|
| MCP tool list/call | M | **Frontend does not call MCP.** Live module exists at `GET/POST /mcp/{server}` (not the `contracts/mcp-contract.yaml` paths `/mcp/tools` and `/mcp/call`). Independent `SIGNOFF.md` claims M1–M4 PASS. **Not a frontend blocker today.** |
| `/traces`, `/metrics` (product UI) | O | **Not built** as FastAPI routes on `app`. Compose runs `otel-collector` only. Provisional tests talk to a mock. Frontend has no observability UI. |

Nothing in A2 maps to Block M or Block O. There is no frontend feature to mark “blocked on M/O.”

### A3.5 Auth / scope mismatches that will fail real round-trips even when the path exists

1. **Register vs Block N invite** — see A3.1 row 2. Highest severity. Source of truth is current Block N (`require_admin`, generated password). Frontend comment still describes suhani’s unauthenticated `admin.py`.
2. **Member scopes vs connector UI** — `scopes_for_role("member")` = `["search.read", "document.read"]`. Connector GETs need `connectors.read`; mutations need `connectors.write`. A successful native **member** login will 403 every connector call. Admin role JWTs include those scopes. Frontend `isAdmin()` also requires `connectors.write` or `admin.*`, so a member never sees Admin, but **does** see Connectors and will error.
3. **Dev admin override** — adds scopes in the **UI only**. API still uses the real JWT. Override cannot make connector calls succeed for a member token.
4. **Refresh tokens** — stored, unused; backend refresh grant is 501. Access token TTL expiry will silently fail `isAuthenticated()` via `exp` and dump the user to a logged-out zustand state without a refresh attempt.
5. **Error envelope** — mixed `detail` vs `{error: {message}}`. Client handles both. Not a blocker.
6. **`getMe` unused** — login trusts the login response + local JWT decode. Will not pick up `must_change_password` until something calls `/me` or reads the extra login fields.

### A3.6 JWT claims (frontend vs Block A)

| Claim | Frontend uses? | Backend issues? |
|-------|----------------|-----------------|
| `sub` | decode only | Y (principal_id) |
| `tenant_id` | decode only | Y (exactly one) |
| `scopes` | admin gating, connector `enabled` | Y |
| `iat` / `exp` | expiry check | Y |
| `iss` / `jti` | no | Y |
| `role` | no (admin is derived from scopes) | Y on native login |
| `token_version` | no | Y on native login |
| `must_change_password` | no | Y on native login |

Header expected by Block A middleware: `Authorization: Bearer …`. Frontend sends that. Optional `X-Tenant-ID` matching (`require_matching_tenant`) is **not** sent; connector routes use JWT tenant vs resolved tenant instead.

---

## A4. Stop line

This file is the Part A deliverable.

**Pulled:** `frontend/` from `origin/suhani` onto branch `frontend-integration` (off Pratham `5ce77b1`).  
**Not pulled:** any `backend/` (or other) path from `suhani`.  
**Not done in Part A:** pointing chat/search/documents at real J/K/L, fixing register, adding `.env.example`, smoke tests.

Part B must re-read this file before changing a line of frontend integration code. Backend A–N stays unmodified.
