# BUILD PASS — Google Workspace Connector (Drive + Gmail)
**Date:** 2026-08-18  
**Branch:** `Pratham`  
**Type:** Real build. Not a signoff.  
**Manual OAuth:** pending Ach (see §6.3).

---

## 6.1 Survey findings (§2)

### 2.1 Plugin framework (Block B) — already present, Google is the first connector

This codebase already has Block B’s plugin interface. A new connector is **not** a parallel tree; it must implement `BaseConnector` and drop a `manifest.yaml` under `backend/app/connectors/`.

| Piece | Real location | What it requires |
|---|---|---|
| Abstract contract | `backend/app/core/base_connector.py` | `get_source_type`, `get_valid_token`, `fetch_delta`, `fetch_deleted_ids`, `transform` → `UnifiedDocument` |
| Registry | `backend/app/services/registry.py` | Recursive discovery of `BaseConnector` subclasses + `manifest.yaml` |
| Manifest schema | `backend/app/connectors/google/manifest.yaml` | `source_type`, `display_name`, `auth_type`, `oauth_scopes`, `services.{google_drive,google_gmail}.allowed_metadata_keys` |
| Blind orchestrator | `backend/app/services/sync.py` | Two-pass: deletions then delta; never imports connectors by name |
| Indexer | `backend/app/services/indexer.py` | Allowlists metadata via the registry, embeds, upserts Qdrant |
| Celery | `backend/app/workers/celery_app.py` + `tasks.py` | `backfill_tenant_source`, Drive/Gmail incremental tasks |

Google already existed as a stub package (`DriveConnector`, `GmailConnector`, `GoogleOAuthManager`, Drive/Gmail API clients, webhooks). What was **not** real: OAuth callback, persistent encrypted tokens, Drive export/download, Gmail filtering, auto-sync on connect, or status chips backed by runtime state.

Per-connector Celery queue (architecture change #8) was **not** declared. Workers listened only to the default `celery` queue. This session added `task_routes` → queue `google` and updated compose worker commands to `-Q celery,google`.

No other production connector exists. Google is first. The old standalone layout (`auth.py` / `drive.py` / `gmail.py` / `google_sync_tasks.py`) was **not** found as a sibling repo on this machine; design was taken from the prompt’s description and from the stubs already in this tree.

### 2.2 Block C — connector should emit raw objects, not own canonical writes

`backend/app/services/pipeline.py` `Pipeline.process_raw(raw, source_type, tenant_id)` is the real Block C entry:

- Input: **raw source dict** (Drive `files` object or Gmail `messages.get` payload) plus `source_type` ∈ `{google_drive, google_gmail}`.
- Source ACLs: Drive `permissions[]` with `type`/`emailAddress`/`role`; Gmail mailbox owner via `_mailbox_email` or `Delivered-To`. Identity hints are emails — Block C’s `IdentityResolver` creates/matches `Principal` rows. That matches §14.3 (raw Google emails in, canonical principals out).
- Output: `CanonicalDocument` + compiled `ACLEntry` + `UnifiedDocument` with `user:<uuid>` / `group:<uuid>` permissions.

The old reference design’s connector-owned `documents` table write is **not** correct here. Block C owns canonicalization. The connector’s job ends at hydrated raw objects (`_extracted_text`, `permissions`, `_mailbox_email`).

`GoogleDriveNormalizer.extract_text` was a placeholder (filename / `_test_extracted_text`). This session taught it to prefer `_extracted_text` attached by the connector after Drive export/download. `CanonicalRepo` still defaults to **in-memory** (`use_memory=True`) — see §6.4.

### 2.3 Storage and secrets (Block D)

- **Credentials table in this schema:** `tenant_connectors` (`backend/app/models/tenant_connector.py`) with `credential_ref` = Vault **key name only**. Admin connectors already store JSON in Vault via `vault_client.set_secret`. There is **no** `source_accounts` table in the current models.
- **Cursors / watches:** `sync_cursors` via `backend/app/services/cursor_store.py` (Postgres, durable).
- **`EncryptionClient`** (`backend/app/storage/encryption/encryption_client.py`): envelope encryption via pgcrypto. `encrypt()` **requires a synchronous `db_client`**. That client is not wired into FastAPI or Celery. Tests construct `EncryptionClient(None, vault_client)`. Using it for OAuth blobs would invent a second DB connection path.

**Decision:** do **not** call `EncryptionClient.encrypt()`. Reuse the vault-key-reference discipline it (and admin connectors) already follow: Fernet key stored in Vault under `kv/platform/google-oauth-fernet` (bootstrapped from `TOKEN_ENCRYPTION_KEY` when present, never logged); token JSON encrypted with Fernet; ciphertext stored in Vault at `kv/tenant-{id}/google-oauth` and in Redis so `MockVaultClient` (process-local) cannot strand Celery workers. `tenant_connectors.credential_ref` holds the Vault key **name**.

Config names actually read (confirmed, values not printed):

| Env name | Settings field | Loaded |
|---|---|---|
| `GOOGLE_CLIENT_ID` | `google_client_id` | yes |
| `GOOGLE_CLIENT_SECRET` | `google_client_secret` | yes |
| `GOOGLE_REDIRECT_URI` | `google_redirect_uri` | yes, includes `connectors/google/callback` |
| `TOKEN_ENCRYPTION_KEY` | `token_encryption_key` | yes |

Previously `connectors.py` used `getattr(settings, "GOOGLE_CLIENT_ID", "")` which always missed the Pydantic field `google_client_id`. AliasChoices were added so the env names are first-class.

### 2.4 Chunking / embedding / indexing (E, F, G)

- Block E prose chunker (`backend/app/services/chunking/prose.py`) handles Drive/Gmail extracted text. **It is not invoked** when a canonical document is written. `indexer.bulk_index` embeds `title + content` as one vector and upserts Qdrant.
- There is no Kafka producer from this consolidated backend onto `KAFKA_TOPIC_CANONICAL`, so the split-service E consumer is not on this path.
- Lexical (F) `OpenSearchStore.index_batch` exists but the Block B indexer does not call it.

Connectors therefore get a document into **vector** search by going through `indexer.bulk_index`. They do not currently trigger E→F automatically. Reported in §6.4; not patched (out of scope — do not modify F/G).

### 2.5 Chat retrieval (Block L)

Block L tools call the federator (`backend/app/services/query_federator/__init__.py` → `app.api.v1.search.federated`). Fan-out is lexical + vector with ACL terms. **No source-type filter** excludes `google_drive` / `google_gmail`. Once Google docs are in Qdrant (and optionally OpenSearch), chat can cite them with no L changes. Vector-only is enough for a degraded-but-working federator (`degraded=true` if lexical is empty/down).

### 2.6 Frontend (already from `suhani`)

`frontend/components/connectors/connector-card.tsx` + `frontend/lib/api/connectors.ts`:

- One Connect button → `GET /connectors/google/authorize` → `window.location = authorization_url`.
- Drive and Gmail are **separate** backend source types (`google_drive`, `google_gmail`) with `GET .../status`, `POST .../backfill` (Resync), `POST .../disconnect`.
- Status used `cursor` as “connected” and `watch_active` as live updates. No `files_indexed`.

That contract matches Block B (one OAuth, two services). Backend was matched to it; frontend chips now also read `details.connection_status` / `details.files_indexed`.

---

## 6.2 What was built

### OAuth flow

1. `GET /api/v1/connectors/google/authorize` (JWT + `connectors.write`) builds the Google URL via `GoogleOAuthManager.build_authorization_url` with combined Drive+Gmail+userinfo scopes, `access_type=offline`, `prompt=consent`.
2. `state` is base64url JSON `{tenant_id, user_id, nonce}` (`oauth_state.py`). Nonce is stored in Redis (10 min) for CSRF.
3. `GET /api/v1/connectors/google/callback` is **unauthenticated** (Google redirects without our JWT). Validates state, exchanges `code`, encrypts tokens, upserts `tenant_connectors` for both sources with `credential_ref` only, writes `mailbox_email` onto the token blob, sets status `syncing`, **enqueues `backfill_tenant_source` for `google_drive` and `google_gmail` immediately**, redirects to `{FRONTEND_URL}/connectors?google=connected`.
4. Token refresh failure in `GoogleOAuthManager._refresh_token` sets both sources to `needs_reauth`.

### Sync logic (adapted from the old design, on this framework)

| Old design idea | Where it lives now |
|---|---|
| MIME handling + Docs export | `content.py` + `DriveClient.export_file` / `download_file`; skip folders/shortcuts |
| Drive Changes API incremental | already `fetch_since_page_token` → `process_drive_notification` |
| Permission fetch | `_hydrate_files` calls `permissions.list` when `files.list` omitted ACLs |
| Gmail promo/OTP filter | list query `-category:promotions -category:social -category:forums -in:spam -in:trash` + label/subject OTP skip |
| Bounded worker pool | `asyncio.Semaphore(5)` Drive hydrate; `Semaphore(8)` Gmail `messages.get` |
| Status `active`/`syncing`/`error`/`needs_reauth` | `status_store.py` (Redis); exposed on `GET .../status` `details` |
| Celery task, own queue | `backfill_tenant_source` routed to queue `google` |

Raw objects go through Block C when `Pipeline.process_raw` can import (`sync.py` best-effort); otherwise `connector.transform()` still indexes (Block B tests keep working). Extracted Drive text is on `_extracted_text` for both paths.

Dummy in-memory `TokenStore` in Celery was replaced with `PersistentGoogleTokenStore`.

### Encryption approach (explicit)

**Not** `EncryptionClient.encrypt()` — it needs a pgcrypto `db_client` that this process does not have. **Yes** vault-backed key reference + Fernet, same discipline as §15.2 / admin `credential_ref`. Ciphertext in Vault + Redis. `TOKEN_ENCRYPTION_KEY` is only a local bootstrap for the vault Fernet key.

### Auto-sync on connect

OAuth callback success → `backfill_tenant_source.delay` for both Drive and Gmail. Resync remains `POST /connectors/{source}/backfill`. Connect does not require a second click.

### Frontend

Status chips: Not connected / Syncing / Connected / Needs re-auth / Error. Ingestion tile shows `files_indexed` when the backend reports it. Connect/Resync/Disconnect already pointed at the real endpoints; they now have a real callback and real status payload behind them.

### Files created

- `backend/app/connectors/google/token_store.py`
- `backend/app/connectors/google/oauth_state.py`
- `backend/app/connectors/google/status_store.py`
- `backend/app/connectors/google/content.py`
- `backend/app/connectors/google/pipeline_bridge.py`
- `backend/tests/test_google_oauth_flow.py`

### Files changed (`.bak` taken first)

- `backend/app/core/config.py` — `AliasChoices` for `GOOGLE_*`, `FRONTEND_URL`, Celery URLs
- `backend/app/api/v1/connectors.py` — authorize via manager + state; callback; richer status; auto-sync
- `backend/app/connectors/google/oauth.py` — `needs_reauth` on refresh fail; `google_oauth_from_settings`
- `backend/app/connectors/google/clients/drive_client.py` — `export_file`, `download_file`
- `backend/app/connectors/google/clients/gmail_client.py` — `get_profile`
- `backend/app/connectors/google/services/drive_service.py` — full list, hydrate, extract
- `backend/app/connectors/google/services/gmail_service.py` — query, OTP filter, bounded fetch
- `backend/app/workers/tasks.py` — persistent token store, status, mailbox from token blob
- `backend/app/workers/celery_app.py` — `task_routes` queue `google`
- `backend/app/services/sync.py` — best-effort Block C `process_raw`
- `backend/app/normalizer/strategies/google_drive.py` — consume `_extracted_text`
- `frontend/lib/api/connectors.ts`, `frontend/components/connectors/connector-card.tsx`
- `docker-compose.yml`, `backend/docker-compose.yml` — worker `-Q celery,google`

`SIGNOFF.md` was not touched. No git commit/push/stage.

---

## 6.3 Verification results (§4)

### Confirmed automatically

**Config names (values not printed):**

```
google_client_id_configured True
google_client_secret_configured True
google_redirect_uri_configured True
google_redirect_has_callback True
token_encryption_key_configured True
frontend_url http://localhost:3000
```

**OAuth URL generation** — `tests/test_google_oauth_flow.py::test_authorize_endpoint_returns_google_url` hit the real FastAPI route with a JWT. Response 200. URL host `accounts.google.com`, path `/o/oauth2/v2/auth`, `client_id` present (test double, not the live secret), `redirect_uri=http://localhost:8000/api/v1/connectors/google/callback`, scopes include `drive.readonly` and `gmail.readonly`, `access_type=offline`, `state` decodes to tenant_id + user_id + nonce.

**Token encryption round-trip** — `test_token_blob_encrypt_decrypt_roundtrip` and `test_persistent_token_store_roundtrip_memory_fallback`. Ciphertext does not contain the dummy token strings; decrypt restores the original JSON. Dummy values only; live tokens never printed.

**Regression:** `test_signoff_block_ab_integration` AB1–AB6 (including AB6 eager backfill enqueue) and Block B Drive/Gmail signoff tests: **36 passed** in the full B+AB+normalizer run after the AB6 Redis/profile fix; follow-up OAuth+AB6+AB3+Drive normalizer: **14 passed**.

### HANDOFF — Ach must complete Google login once

Completing consent cannot be scripted. **Stop here for end-to-end.**

After backend + frontend are running (API `:8000`, UI `:3000`, Celery worker with `-Q celery,google`):

1. Sign in to the app as a user with `connectors.write` + `connectors.read`.
2. Open **Connectors** → Google Workspace → **Connect**.
3. Complete Google login + consent (Drive readonly + Gmail readonly). Google will redirect to `/api/v1/connectors/google/callback`, which will store tokens and **start both backfills without a Resync click**.
4. Confirm Drive/Gmail chips move to **Syncing** then **Connected**, and ingestion shows a non-zero indexed count.
5. Ask chat something that exists in that Drive/Gmail account and check the answer is cited.

Until that consent happens, do **not** treat the connector as end-to-end done. Indexed-document counts and a Block L cited answer are unverified.

---

## 6.4 Noticed but not fixed

1. **Block C `CanonicalRepo` is in-memory** (`use_memory=True`). ACL compilation runs in-process for the Celery worker; it does not persist canonical rows/ACL entries to tenant Postgres. Query-time ACL for chat therefore relies on whatever `UnifiedDocument.permissions` the indexer wrote into Qdrant, not on compiled ACL tables.
2. **E is not on this path.** Prose chunker exists and is suitable for Drive/Gmail text; `indexer.bulk_index` embeds the whole document. No Kafka canonical publish.
3. **F (lexical) is not written** by the Block B indexer. Federator will degrade to vector-only for Google docs until something indexes OpenSearch. Not modified (F is out of scope).
4. **No `source_accounts` table.** Per-user OAuth is stored as a tenant-level Vault blob keyed by tenant_id (one Google account per tenant in this UI). Fine for the current Connectors card (one Connect button); not multi-user mailbox isolation.
5. **Drive images / scanned PDFs** go through `FakeOCRService` in the connector hydrate path so Celery does not require Tesseract. OCR-quality Google files will have weak text until real OCR is wired in the worker.
6. **Gmail `fetch_deleted_ids`** no longer pings a dummy Pub/Sub watch when there is no cursor (that was a quota foot-gun). First backfill deletion pass is empty until a history id exists.
7. **Watch/live updates** still depend on Drive webhook + Gmail Pub/Sub config (`GOOGLE_PUBSUB_*`). Connect + poll/backfill work without them; the “Live updates” chip stays Off until watches register.

---

**Next step (Ach):** click Connect in the running app and finish Google consent. After that, this same branch can verify indexed counts and a cited Block L answer against real Drive/Gmail content.
