# Diagnostic — Does skipping `TenantMiddleware` invalidate N1–N3?

**Date:** 2026-08-17  
**Type:** Diagnostic only. Part B was not run. **This file is not `SIGNOFF.md`.**

**HEAD:** `5ce77b1a97f3bf0ea0ba980282940f517e7ad911` (`Add: Block N completed and tested`)  
**Branch:** `Pratham`  
**Repo:** `logicinnovationlabs/Sync-AI-Final`

No files edited. No commits, no pushes, no `SIGNOFF.md` edits.

---

## 4.1 What `TenantMiddleware` actually does

Registered on the production app in `backend/app/main.py`:

```86:87:backend/app/main.py
# Tenant resolution middleware
app.add_middleware(TenantMiddleware)
```

Every live request through that app, including `/api/v1/admin/*`, goes through it. CORS is the only other `add_middleware`.

The implementation is `backend/app/middleware/tenant_middleware.py`. Side effects, from the code not the docstring:

**Reads**

- `request.url.path` — skip list is only `/`, `/docs`, `/openapi.json`, `/health`, `/redoc`. Admin paths are not skipped.
- `Authorization` — only if it starts with `Bearer `.
- JWT payload via `token_service.decode_without_validation` (`verify_signature: False`). Not `validate_token`. No expiry, signature, or revocation check.
- `payload["tenant_id"]`, then `tenant_resolver.resolve(tenant_id)`.

**Sets**

- On success only: `request.state.tenant = routing` (`TenantRouting`).

**Does not set** if there is no Bearer token, no `tenant_id` claim, or any exception.

**Enforcement: none.** Both expected and unexpected failures are swallowed. The handler always runs:

```66:80:backend/app/middleware/tenant_middleware.py
            except _EXPECTED_SOFT_FAIL as e:
                # Expected: missing tenant, bad JWT shape, schema/DB soft errors.
                # Route-level auth deps remain the real 401/403 gate.
                logger.debug("Tenant middleware soft-fail: %s", e)
            except Exception as e:
                # Still soft-fail (middleware is optional pre-resolve) but never silent:
                ...
                logger.warning(...)

        response = await call_next(request)
        return response
```

It never returns 401/403/404. It never rewrites the path, body, or JWT. It never opens a tenant DB session. A failed pre-resolve leaves `request.state.tenant` unset and still calls the route.

That matches the file’s own comment: resolution failures are non-fatal; route-level auth deps are the 401/403 gate. The middleware is an optional cache-warming pre-resolve (resolver itself caches in Redis), plus DEBUG/WARNING logs. It is not the tenant-isolation boundary.

---

## 4.2 Do N1–N3’s admin routes depend on what it sets?

Repo-wide readers of `request.state`:

| Location | What it sets/reads |
|----------|-------------------|
| `TenantMiddleware.dispatch` | **writes** `request.state.tenant` |
| `mcp_gateway/identity.py` | writes `mcp_tenant_id` / `mcp_principal_id` / `mcp_jti` — Block M, not admin |

**Nothing in `backend/app/` reads `request.state.tenant`.** Grep for `state.tenant` and `.state.` has no other hits.

Admin handlers N1–N3 call (`users`, `connectors`, `audit`, `sessions`) take tenant context only from FastAPI `Depends`:

```88:90:backend/app/api/v1/admin/users.py
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
```

Same pattern on connectors, audit, and sessions. `tenant.py` bootstrap uses `get_control_plane_session`, not the middleware (and N1 did not call it).

Those deps do **not** look at `request.state`. They re-resolve from the JWT:

```37:95:backend/app/api/deps.py
async def get_current_user(...) -> Dict[str, Any]:
    payload = await token_service.validate_token(token)  # signature, expiry, Redis revoke
    return payload

async def get_tenant(current_user=Depends(get_current_user)) -> TenantRouting:
    tenant_id = current_user.get("tenant_id")
    ...
    routing = await tenant_resolver.resolve(tenant_id)  # independent of middleware
    return routing

async def get_tenant_session(tenant=Depends(get_tenant)):
    async for session in tenant_db_manager.get_session(...):
        yield session
```

Isolation for admin routes:

- Tenant id from **validated** JWT (`get_current_user`), not the middleware’s unverified decode.
- DB session from `get_tenant` → `tenant_db_manager` (JWT tenant), not `request.state.tenant`.
- Admin check: `require_admin` loads `User` with `principal_id` + `tenant_id` from that session.
- Audit `tenant_id` is `str(tenant.tenant_id)` from `get_tenant`, not middleware state.

Where admin handlers take Starlette `Request`, it is only for `client_ip(request)` (`X-Forwarded-For` / `request.client.host`). Not `request.state`.

The slim test app still ran those `Depends(...)` on the real handlers. It overrode `get_tenant` / `get_tenant_session` onto the test Postgres session (same as K’s ASGI tests overriding store). That override is independent of skipping middleware. What the middleware would have added on a live request — an unused `request.state.tenant` and a duplicate `tenant_resolver.resolve` — is not an input to N1–N3’s assertions (audit rows, search latency, `validate_token` after `POST /sessions/revoke`).

---

## 4.3 Verdict: bypass is harmless

N1–N3’s PASS stands.

`TenantMiddleware` is on the production app and runs on real admin requests, but it does not reject or scope those requests. Tenant isolation for `/api/v1/admin/*` is `deps.py` (`validate_token` + `get_tenant` + `get_tenant_session` + `require_admin`). Skipping the middleware in the slim ASGI client does not omit a check a live admin request depends on for correctness.

This is not the K in-memory-store shape (wrong backend) or the old L1/L4 shape (criterion not exercised). The handlers and Block A `validate_token` path N1–N3 were rewritten to hit are still the live ones. The skip only drops an optional, non-enforcing pre-resolve that no admin code reads.

Caveat, named not expanded: a live request still pays for middleware’s extra unverified decode + `resolve` (Redis cache / control-plane). N2’s p95 is the handler + deps on the slim app, not middleware overhead. Isolation and audit completeness do not depend on that extra hop. Not re-measured.

## 4.4 Part B

Not run. Part A found the bypass does not matter.

Stopped here. No `SIGNOFF.md` edits, no O, no commit, no push.
