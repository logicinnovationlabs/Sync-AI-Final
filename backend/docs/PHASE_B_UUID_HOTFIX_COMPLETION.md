**Status: IMPLEMENTED — AWAITING INDEPENDENT VERIFICATION**

Phase B applied the UUID widen, stamped tenant DBs at `005` then upgraded to `006`, and re-ran C1/C2/C4 against live tenant databases.

## UUID type widen

In `backend/app/core/models.py` (`.bak` taken first), pydantic `UUID4` became plain `UUID` on:

- `Principal.id`
- `ResolvedIdentity.principal_id`
- `ACLEntry.principal_id`
- `CanonicalDocument.owner_principal_id`, `creator_principal_id`, `last_modifier_principal_id`

Left as `UUID4`: `Group.id` / `member_principal_ids` / `member_group_ids`, `ACLEntry.group_id`, `ContainerACLEntry.principal_id` / `group_id`, every `tenant_id`. Owner/creator resolution in `pipeline.py` was not changed.

## Schema spot-check before stamp

Compared `users`, `acl_entries`, and `canonical_documents` on `snyq_tenant_alpha` / `beta` / `gamma` against control-plane (real Alembic). **Column names, types, and nullability match.** Non-blocking drift only:

- Control-plane has extra **server defaults** (`is_deny=false`, `content=''`, `status='active'`, etc.) that `create_all` tenants lack.
- Control-plane `users` has extra unique indexes (`ix_users_email_unique`, `users_email_key`, `users_idp_subject_key`).

None of that blocks `006` (queue table only). No tenant was aborted.

## Manual `pending_identity_queue` on alpha: **dropped and recreated**

Live tenant tables (from Phase C SQL) already matched Alembic `006`, including `first_seen_at DEFAULT now()`. They were still dropped so the live table is not the hand patch.

`backend/scripts/migrate_tenant_dbs.py` listed tenants from the control-plane registry, dropped `pending_identity_queue` when not at `006`, stamped `005_merge_heads`, then `alembic upgrade head`. Result:

| DB | Action |
|---|---|
| `snyq_tenant_alpha` | dropped manual table → stamp `005` → upgrade `006` |
| `snyq_tenant_beta` | same |
| `snyq_tenant_gamma` | same |

**`snyq_tenant_alpha` now has the Alembic-created table** (`first_seen_at DEFAULT now()`, indexes `pending_identity_queue_pkey`, `ix_pending_identity_queue_tenant_email_resolved`, `uq_pending_identity_tenant_doc_email`). That is the DB C2/C4 ran against.

## Re-verification

**C1 (tenant path):** stamp-then-upgrade put all three at `006_pending_identity_queue`. Extra round-trip on `snyq_tenant_gamma`: `downgrade -1` → table gone, version `005_merge_heads`; `upgrade head` → table back with `now()`, version `006`.

**C2 (alpha, uuid5 native principal `95d1dbb9-…` version nibble `5`):**

- unmatched share queued, no ghost principal
- invite drain bound `resolved_principal_id` to `users.principal_id`
- `drive_share` ACL row written
- JWT `sub` matched
- `GET` document **200** via `PostgresACLChecker`

**C4 (alpha):**

- 5 unmatched emails queued, then 5/5 drained on invite
- 2 existing users (`member@synq.dev`, `admin@synq.dev`) bound immediately, no queue row (after persist via `replace_acl_entries`, same as `pipeline.py`)
- mixed-case/whitespace `  MEMBER@synq.dev  ` bound to `member@synq.dev`, not admin

Unit tests: `tests/test_drive_identity_bind.py`, `test_identity_resolver.py`, `test_acl_compiler.py` — 16 passed.

## Files

- `backend/app/core/models.py` + `backend/app/core/models.py.bak`
- `backend/scripts/migrate_tenant_dbs.py` (new)

## Still out of scope

- `opentelemetry.instrumentation.celery` import (blocks real `app.main` `/auth/login`)
- owner/creator/last_modifier **behavior** in `pipeline.py`
- webhook ACL compile, group/domain expansion, folder inheritance, `filter.py` fail-open

Clarification: the C4 existing-user check initially failed because the verification harness didn't call replace_acl_entries after compile(); the drain path and the 5-unmatched-email cases persist directly and were unaffected. No product code was changed. See follow-up trace for details.
