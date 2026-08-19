# Google Connector Diagnose — 401 + “Token has expired”
**Date:** 2026-08-18  
**Branch:** `Pratham`  
**Type:** Diagnose-first. No connector rebuild. No `SIGNOFF.md` edits, no commits, no pushes.

---

## 6.1 Part A — 401 root cause

**Root cause: expired SynQ AI access JWT, not a broken connectors auth dependency, and not a Google OAuth failure.**

Evidence:

1. The red card text **“Token has expired”** is the JWT validator’s message, not a Google connector status string. `token_service.validate_token()` raises `InvalidTokenError("Token has expired")` on `jwt.ExpiredSignatureError`. `get_current_user` turns that into `UnauthorizedError` (401). The Connectors card renders `ApiError.message` in red when `/status` fails:

```210:210:backend/app/services/token_service.py
            raise InvalidTokenError("Token has expired")
```

```123:128:frontend/components/connectors/connector-card.tsx
        {status.error ? (
          <span className="text-[0.75rem] text-destructive">
            {status.error instanceof ApiError
              ? status.error.message
              : "Couldn't reach the API"}
```

2. The `/status` router is wired correctly: `Depends(get_current_user)`, `Depends(get_tenant)`, `require_scope("connectors.read")`, mounted in `main.py` as `/api/v1`. Same pattern as backfill/authorize. This is not a stale import.

3. Access TTL is **3600 seconds** (`settings.token_ttl_access=3600`). The frontend stores `refreshToken` but **never calls a refresh endpoint** — `apiFetch` always sends the persisted access JWT. An idle tab past one hour keeps hammering `/status` with an expired bearer.

4. Host uvicorn (there is no `snyq_backend` container) logged the 401s after hours of 200s:

```
INFO: GET /api/v1/connectors/google_drive/status  200 OK   (many, from ~08:49)
INFO: GET /api/v1/connectors/google_drive/status  401 Unauthorized   (~09:47, then again 10:06:41)
INFO: GET /api/v1/connectors/google_gmail/status 401 Unauthorized
```

JWT keys are files on disk (`jwt_private_key_file_exists=True`), so the uvicorn reload at 09:58 did not rotate signing keys. The 09:47 401s happened **before** that reload. Classic TTL expiry.

**Fix applied:** session re-login. No code change.

- `POST /api/v1/auth/login` as `admin@synq.dev` / tenant `alpha` → 200, new Bearer.
- Fresh JWT:

```
GET /api/v1/connectors/google_drive/status  → 200
{"source_type":"google_drive","cursor":null,"watch_active":false,
 "details":{"connection_status":"syncing","files_indexed":0,"token_present":true}}

GET /api/v1/connectors/google_gmail/status  → 200
{"source_type":"google_gmail","cursor":null,"watch_active":false,
 "details":{"connection_status":"syncing","files_indexed":0,"token_present":true}}
```

- Browser re-login (seeded admin) then `/connectors`: Drive and Gmail show **Syncing**, not “Token has expired”. Google **Connect** is enabled. Uvicorn after that login: both `/status` calls **200**.

If the screenshot was from a different browser profile than the IDE browser used here, **sign out and sign back in there too** — that tab still has the expired JWT in `synq-auth` localStorage.

---

## 6.2 Part B — stored Google tokens

**There is no `oauth_tokens` table.** `control_plane` relations: `tenant_connectors`, `sync_cursors`, `refresh_tokens` (app JWTs), etc. No `oauth_tokens`.

SQL:

```
SELECT ... FROM tenant_connectors WHERE source_type LIKE 'google%';
→ (0 rows)

SELECT ... FROM sync_cursors WHERE source_type LIKE 'google%';
→ (0 rows)
```

Google tokens live in `PersistentGoogleTokenStore` (Vault key name + Redis ciphertext), not in `oauth_tokens`.

Inspected store for tenant `df1da93d-eb44-4ddf-af59-d6feec4abf75` (Alpha, from `/status`). **Values not printed.** Shape:

- `token_present=True`
- keys: `access_token`, `refresh_token`, `id_token`, `mailbox_email`, `scope`, `expires_at`, `expires_in`, `token_type`
- `access_is_pending_refresh=False` (not the env-seed dummy)
- `mailbox_email_set=True`
- `expires_at=2026-08-18T05:17:08.335198` (Google access expiry, naive UTC)

This is a **genuine prior OAuth exchange**, not fixture/test-seed data (those would be `pending_refresh` and would not set `mailbox_email` / `id_token`). **Left in place.** Clicking Connect again will refresh through the real consent flow, as specified.

`seed_token_store_from_env` skip-if-exists is still in `backend/app/connectors/google/oauth.py` (the prompt’s path `backend/app/services/connectors/google/` does not exist). `google_refresh_token_set=False` in the running settings. Landmine has not reappeared.

`connection_status=syncing` is derived: no cursor + token present → UI “Syncing”. No files indexed yet (`files_indexed=0`). That is leftover/incomplete first sync, not an expired Google token.

---

## 6.3 Part C — Celery worker

`docker ps`: **no** `snyq_celery_worker`. Only `block-e-chunking-celery-worker-1` (different app).

Host process **is alive**:

```
celery  PID 16808  started 2026-08-18 10:02:35
```

That is last session’s host worker (`celery@Ishu`, `-Q celery,google`, broker `redis://localhost:6379/1`). Startup log still shows both queues; last proven consume was `google_queue_ping` succeeding. No restart required this session.

**Not durable.** This is a manually started terminal process. If that terminal dies, the `google` queue has no consumer and Connect-triggered backfill will sit unacked. Needs a Compose service or Windows service before day-to-day reliance. **Not built this session.**

---

## 6.4 Part D — env vars in the running backend

`docker exec snyq_backend printenv` **cannot run**: there is no `snyq_backend` container. The API is host uvicorn on `:8000` (started 08:49 IST, `--reload`).

Names only, loaded via the same Settings object that process uses (all four **set**):

```
GOOGLE_CLIENT_ID= True
GOOGLE_CLIENT_SECRET= True
GOOGLE_REDIRECT_URI= True
TOKEN_ENCRYPTION_KEY= True
```

(`google_refresh_token` remains unset.)

---

## 6.5 Go / no-go

**Go — the Connectors page is ready for a real manual OAuth click**, after a fresh SynQ login in the browser tab that showed the 401s.

The 401 + red “Token has expired” was the one-hour **app** access JWT. Connector OAuth, encryption, and extraction were not the failure. `/status` is 200 for Drive and Gmail with a new session. A real Google token is already stored for Alpha (prior consent); Connect again will re-consent/refresh. Celery is listening on `google` right now. All four Google/encryption env names are present on the host API.

**Do this in the tab that had the screenshot:** sign out → sign in as `admin@synq.dev` → Connectors should show Syncing (not red expiry) → click **Connect**.

### Named, not fixed

- Frontend never refreshes the access JWT; this 401 will recur every 3600s on an idle tab.
- Host Celery is not a restart-on-boot service.
- `tenant_connectors` has no Google rows even though Redis/vault has a real token (callback upsert is best-effort). Status still works via the token store.
- Default `redis_url` still uses Docker DNS `redis`; host processes must keep `REDIS_URL=redis://localhost:6379`.
