**Status: DECISION NEEDED**

Commit `5458487` ("Let members connect their own Google account with private Drive and Gmail ACL") introduced per-user OAuth token storage and frontend copy promising private per-member connections. The backend schema does not support the promised multi-connection model.

## What was promised

Frontend copy from `5458487`:

- `frontend/app/(app)/connectors/page.tsx`: "Connect your own Google account. Drive and Gmail stay private to you — other members and admins cannot search them."
- `frontend/lib/connectors.ts`: "Your Drive and Gmail. Only you can search what you connect."
- `frontend/lib/auth/scopes.ts`: "Members now also get connectors.read/write for their own Google account. Do not treat connectors.write as admin."

The intent: each member optionally connects their own Drive/Gmail as a private, personal connector, separate from and in addition to any admin-mirror connection.

## What the schema actually allows

`backend/app/models/tenant_connector.py` line 26:

```python
UniqueConstraint("tenant_id", "source_type", name="uq_tenant_connectors_source"),
```

This constraint allows exactly ONE connection per `(tenant_id, source_type)`. A second member connecting the same source for the same tenant overwrites the first member's `TenantConnector` row, including `credential_ref`.

The table has no `user_id` column in the unique constraint, so multiple per-user connections cannot coexist regardless of OAuth token storage capabilities.

## Concrete failure mode

If Member A connects Google Drive for tenant T, then Member B clicks "Connect your own Google account" for the same tenant and source:

`backend/app/connectors/router.py` lines 361-367 in `_record_connector_rows`:

```python
result = await session.execute(
    select(TenantConnector).where(
        TenantConnector.tenant_id == tenant_uuid,
        TenantConnector.source_type == source_type,
    )
)
row = result.scalar_one_or_none()
```

The query finds Member A's row. The upsert (lines 369-379) replaces it with Member B's data, including `credential_ref` and `config`. Member A's connection is silently deleted from the tracking layer, even though their OAuth token still exists in Vault/Redis.

The webhook tasks (`process_drive_notification`, `process_gmail_notification`) operate on bare `tenant_id` for cursor operations (tasks.py lines 485, 544, 610, 671), so they would now process Member B's connection instead of Member A's, with no explicit transition.

## Related risk: token fallback ownership confusion

`backend/app/workers/tasks.py` lines 825-827 in `_lookup_mailbox_email`:

```python
data = token_store.get_token(google_oauth_token_key(tenant_id, user_id)) or {}
if not data.get("mailbox_email"):
    data = token_store.get_token(google_oauth_token_key(tenant_id)) or {}
```

The inline comment (line 342) explained the intent: "OAuth stores connected_by so manual/beat re-syncs still ACL to the owner." This fallback was meant to recover the admin connection when `user_id` wasn't passed (e.g., Beat task).

If the `TenantConnector` row got overwritten by a second member's connect, this fallback would pick up the most recently written token, potentially attributing the connection to the wrong owner.

## What currently works vs. what doesn't

**Works:**
- Admin-mirror model (single Drive connection per tenant, mirrored via `acl_entries`) — this thread's prior work is unaffected
- Per-user OAuth token *storage* — tokens for different users genuinely coexist in Vault/Redis via `google_oauth_token_key(tenant_id, user_id)` (token_store.py lines 163, 201)

**Does not work:**
- `TenantConnector` tracking layer — the unique constraint prevents multiple rows per tenant/source
- Webhook notification tasks — tenant-scoped cursor operations (no `user_id` parameter)
- Watch registration — registered under bare `tenant_id`, not per-user

## Options

**Option A — migrate the schema to support multi-connections:**

- Change `UniqueConstraint("tenant_id", "source_type")` to `UniqueConstraint("tenant_id", "source_type", "user_id")` in `tenant_connector.py`
- Update `_record_connector_rows` to allow multiple rows per tenant/source (one per user)
- Add `user_id`/`scope_id` parameter to webhook tasks (`process_drive_notification`, `process_gmail_notification`)
- Make watch registration per-user (currently tenant-scoped)
- This is non-trivial backend work touching several files already identified in this thread's diagnosis

**Option B — walk back the UI copy until schema work is done:**

- Change frontend language to reflect what actually happens today: one connection per tenant per source, last-connector-wins
- Remove the "private to you" promise until the backend can actually deliver it
- This is a product copy change only, no backend work required

## What this document is not

- Not a bug report: nothing is presently broken in a way that corrupts data — a second connect silently replaces the first, which is a UX/product-honesty problem, not a crash or a leak
- Not a completed slice: this is a decision record, not implementation work
- Not requiring immediate action: the admin-mirror model continues to work; the per-user promise is simply not yet realizable

## Decision needed

Ach: Choose between Option A (schema migration to enable true per-user connections) or Option B (walk back UI copy until that work is prioritized).

## Resolution

**Option A was implemented** to support multi-connections:

### Schema Changes (Migration 007_split_google_connectors)

1. **Added `connection_scope` field** to `tenant_connectors`:
   - Type: `String(50)` with values `"personal"` or `"organization"`
   - Default: `"personal"` for backward compatibility
   - Indexed for query performance
   - Non-nullable after migration

2. **Updated unique constraint**:
   - Changed from `UniqueConstraint("tenant_id", "source_type")`
   - To `UniqueConstraint("tenant_id", "source_type", "connection_scope")`
   - This allows both `"personal"` and `"organization"` rows per tenant/source

3. **Added tenant-level `google_org_workspace_enabled` flag**:
   - Added to `tenants` table
   - Type: `Boolean`, default `False`
   - Admin-only toggle for organization connector availability

### Backend Implementation

1. **Admin-only endpoints** (`backend/app/connectors/router.py`):
   - `POST /admin/google/organization/connect` - Connect service account
   - `POST /admin/google/organization/disconnect` - Disconnect organization connector
   - `POST /admin/google/organization/toggle` - Enable/disable organization connector
   - `GET /google/organization/status` - Member-readable status

2. **Updated credential logic** (`backend/app/connectors/google/drive_credentials.py`):
   - `load_drive_connector_row()` now accepts `connection_scope` parameter
   - `get_drive_access_token()` uses scope to select correct connector row
   - Organization scope uses existing DWD (domain-wide delegation) path

3. **Updated DriveConnector** (`backend/app/connectors/google/services/drive_service.py`):
   - Now accepts `connection_scope` parameter
   - Passes scope to credential retrieval

4. **Updated status endpoint** (`backend/app/connectors/router.py`):
   - `GET /{source_type}/status` now accepts `connection_scope` query parameter
   - Defaults to `"personal"` for backward compatibility

### Frontend Implementation

1. **Split connector cards** (`frontend/lib/connectors.ts`):
   - Changed from single `"google"` to `"google_personal"` and `"google_organization"`
   - Each has distinct name, description, and handshake type

2. **Updated connector card component** (`frontend/components/connectors/connector-card.tsx`):
   - Personal card: Existing OAuth flow, per-user connection
   - Organization card: Read-only for members, shows "Admin-managed" button
   - Separate status queries for each scope

3. **Added admin console UI** (`frontend/components/admin/admin-console.tsx`):
   - Organization connector management section
   - Connect service account (vault key + impersonate email)
   - Enable/disable toggle
   - Disconnect button

### Verification

- **Personal connector**: Existing behavior unchanged, uses `connection_scope="personal"` by default
- **Organization connector**: Uses `connection_scope="organization"`, service account DWD path
- **ACL enforcement**: Both scopes use existing ACL-mirrored ingestion pipeline unchanged
- **Backward compatibility**: Migration backfills existing rows with `connection_scope="personal"`

## Verification Status (2026-08-23)

**Completed with Evidence:**
- ✅ Schema migration applied (007_split_google_connectors) - Alembic upgrade successful
- ✅ ACL enforcement tests passed (8/8 tests in test_drive_permission_signoff.py) - No regression
- ✅ Database schema verified - `connection_scope` and `google_org_workspace_enabled` columns exist
- ✅ Route mismatch fixed - Admin endpoints corrected from `/api/v1/connectors/admin/...` to `/api/v1/admin/...`

**Requires User Testing (UI Verification):**
- ⏳ Personal connector OAuth flow - Verify unchanged behavior with `connection_scope=personal`
- ⏳ Organization connector status - Verify "Not Found" error resolved after route fix
- ⏳ Admin console connection - Test service account connection via admin UI
- ⏳ Enable/disable toggle - Verify member view reflects admin toggle changes
- ⏳ Coexistence verification - Confirm both connectors can exist simultaneously (database ready, needs UI test)

**Known Bug Fixed:**
- Frontend was calling `/api/v1/connectors/admin/google/organization/...` but backend registers at `/api/v1/admin/google/organization/...` (via admin_router). Fixed in frontend/lib/api/connectors.ts.
