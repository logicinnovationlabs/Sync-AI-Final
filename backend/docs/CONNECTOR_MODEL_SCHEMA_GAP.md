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

The inline comment (line 342) explains the intent: "OAuth stores connected_by so manual/beat re-syncs still ACL to the owner." This fallback is meant to recover the admin connection when `user_id` isn't passed (e.g., Beat task).

If the `TenantConnector` row gets overwritten by a second member's connect, this fallback would pick up the most recently written token, potentially attributing the connection to the wrong owner.

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
