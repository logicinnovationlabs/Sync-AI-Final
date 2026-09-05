# Admin Dashboard UI Verification Report

**This file replaces prior versions.** Earlier "COMPLETE" / "VERIFIED" / "stale dev server was the cause" claims in this path did not match what a human sees at `http://localhost:3000/admin`. This write-up records only what was observed in a real browser in this session (2026-09-02).

It does **not** grade the work PASS/FAIL. It states what was on screen and what was not checked.

---

## 1. Ground truth this session

### Git

```
branch: SYNC_AI_FINAL_
commit: 32b18aca1af86ce63263571360d7620b72822cfa
author: IshuRaj441 <ishuraj441@gmail.com>
date:   Fri Aug 28 16:54:03 2026 +0530
subject: Fix test mock for embed_documents method compatibility with Pratham merge
```

Working tree had additional uncommitted frontend/backend changes. The admin UI work in this session is in those working-tree files, not in `32b18ac` itself.

### Port 3000 before this session

Nothing was listening on port 3000. There was no live frontend to kill. (A previous Next.js process in terminal 1 had already exited after `adapterFn is not a function` / 404s.)

### Port 8000

Docker Compose service `snyq_app` (`snyq_phase_2-app`) was already up and healthy, published at `0.0.0.0:8000`. OpenAPI listed:

- `GET /admin/members` and `GET /api/v1/admin/members`
- `GET /admin/members/{user_id}/documents`
- `POST` / `DELETE /admin/members/{user_id}/documents/{document_id}/access`

Unauthenticated `GET /admin/members` returned **401**, which means the route exists on the running backend.

### Production build

`npm run build` in `frontend/` (Next.js 16.2.12 webpack).

First attempt compiled, then died while prerendering `/connectors`:

```
useSearchParams() should be wrapped in a suspense boundary at page "/connectors"
Error occurred prerendering page "/connectors"
```

That is **not** the admin page. `frontend/app/(app)/connectors/page.tsx` was wrapped in `<Suspense>` so the production build could finish. Connector behavior was not otherwise changed.

Second build:

```
▲ Next.js 16.2.12 (webpack)
- Environments: .env.local
✓ Compiled successfully in 5.4s
  Finished TypeScript in 6.5s
✓ Generating static pages using 15 workers (17/17) in 1034ms

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /admin
├ ○ /chat
├ ○ /connectors
...
○  (Static)  prerendered as static content
```

Then `npm start`:

```
▲ Next.js 16.2.12
- Local:         http://localhost:3000
- Network:       http://192.168.1.14:3000
✓ Ready in 186ms
```

The URL used for the walkthrough: **http://localhost:3000/admin** (after login).

---

## 2. What was actually wrong (not a stale server)

The feature **was already in source** as a second section titled "Member Document Access Control", rendered by `AdminConsole`. It was **not** what you hit first on `/admin`.

Import chain the browser actually uses:

1. `frontend/app/(app)/layout.tsx` → `AppShell`
2. `AppShell` content pane: `min-h-0 flex-1 overflow-hidden` — pages must scroll themselves
3. `frontend/app/(app)/admin/layout.tsx` — if `isAdmin()` is false, `PermissionDenied`; else children
4. `frontend/app/(app)/admin/page.tsx` → `AdminConsole`
5. `frontend/components/admin/admin-console.tsx`

`isAdmin()` is true when JWT scopes include any `admin.*` string (`frontend/lib/auth/scopes.ts`). The seeded account `admin@synq.dev` has those scopes; the layout did not hide the page.

Two concrete bugs made the document-access UI invisible to a human:

1. **The primary list was a different list.** The first block was "Users" from `GET /admin/users`: name, email, role badge. No document count, no "See documents", no Allow/Deny. That is the screen people were describing.
2. **The page could not scroll.** Documents and Connectors wrap their body in `min-h-0 flex-1 overflow-y-auto`. Admin did not. AppShell clips overflow, so Audit / Pending identities / the second member list with counts and Allow/Deny were **below the clip**, not merely "below the fold." Playwright full-page shots of that second section did not match what a person sees in the viewport.

Also in source, not the reason the list was missing, but it would have broken Allow/Deny once reachable: `apiFetch` already `JSON.stringify`s `body`. `setAccessOverride` / `patchAdminUser` / `transferOwnership` passed a pre-stringified string, which would POST a JSON string instead of `{ "access": "deny" }`.

This was **not** "the component was never built." It was built, wired, and then unreachable on the route people actually open.

---

## 3. What was changed this session

| File | Why |
|---|---|
| `frontend/app/(app)/admin/page.tsx` | Same scroll wrapper as Documents/Connectors so `/admin` can scroll. |
| `frontend/components/admin/admin-console.tsx` | Document counts, **See documents**, and Default/Allow/Deny live on the **Members** list that appears immediately under Organization Google Workspace. Duplicate buried section removed. Expanding member B no longer collapses instead of switching. |
| `frontend/lib/api/admin.ts` | Call `/admin/members` (same dual-mount as `/admin/users`). Pass objects as `body`, not double-encoded JSON. |
| `frontend/app/(app)/connectors/page.tsx` | `<Suspense>` around `ConnectorList` so `npm run build` can prerender `/connectors`. No connector logic change. |
| `frontend/lib/api/auth.ts` | `getMe` uses `skipAuthRefresh: true` so login `/me` uses the **new** token. Without this, a leftover `synq-auth` in localStorage made the form show **Token has expired** even when `POST /auth/login` returned 200. |

`.bak` copies were written next to each edited file before the edit.

Backend ACL / override endpoints were **not** rewritten. They were already registered on the running Docker API.

---

## 4. What was seen in the browser this session

Account: `admin@synq.dev` / `AlphaAdmin123!` (from `frontend/lib/dev-login.ts`, not from `.env`). Tenant on localhost is `alpha` (`tenantFromHost` fallback). After sign-in the app navigated to `http://localhost:3000/admin`.

### Members with document counts (no hunting below Audit)

Visible in the viewport after the Google Workspace card:

- Test Admin 2 · admin2@alpha.test · admin · **0 documents** · See documents
- Alpha Admin · admin@synq.dev · admin · **298 documents** · See documents
- Test Member 2 · member2@alpha.test · member · **0 documents** · See documents
- Alpha Member · member@alpha.test · member · **3 documents** · See documents
- Alpha Member · member@synq.dev · member · **0 documents** · See documents
- Test Owner · owner@alpha.test · owner · **0 documents** · See documents
- Test Viewer · viewer@alpha.test · viewer · **0 documents** · See documents

Screenshot: `ui_screenshots/2026-09-02_admin_members_counts.png`

`GET /admin/users` returned the **same 7 emails**. `GET /admin/members` returned the **same 7** with `document_count`. This tenant’s member list is those seven accounts, not a subset.

### See documents

Clicked **See documents** on `member@alpha.test`. Button became **Hide documents**. Nested heading: "Documents assigned to Alpha Member". Three rows with Default/Allow/Deny:

- Q3 Strategy Document · gdrive · Default ACL
- Engineering Handbook · confluence · Default ACL
- Meeting Notes - Architecture Review · slack · Default ACL

Screenshot: `ui_screenshots/2026-09-02_admin_documents_expanded.png`

### Deny, then remove

Set Q3 Strategy Document → **Deny**. Label became **Denied by admin**. Dropdown showed Deny.

Screenshot: `ui_screenshots/2026-09-02_admin_after_deny.png`

Set it back to **Default**. Label became **Default ACL** again.

Screenshot: `ui_screenshots/2026-09-02_admin_after_remove.png`

---

## 5. Real request/response from this walkthrough

Captured from the same browser tab (token not printed).

### Members + counts (page load + repeat GET)

```
GET http://localhost:8000/admin/members
status 200
count 7
[
  { "email": "admin2@alpha.test", "role": "admin", "document_count": 0, "principal_id": "e3095189-d878-50f5-8499-6f89780e4122" },
  { "email": "admin@synq.dev", "role": "admin", "document_count": 298, "principal_id": "d231708a-8d2f-5bb7-a805-fcbfdc19bedb" },
  { "email": "member2@alpha.test", "role": "member", "document_count": 0, "principal_id": "5fe1bf31-d5e4-56b9-97f6-d0ee9805719a" },
  { "email": "member@alpha.test", "role": "member", "document_count": 3, "principal_id": "0c9b84d9-5621-554a-b5ef-e52d5e7358c8" },
  { "email": "member@synq.dev", "role": "member", "document_count": 0, "principal_id": "67245a4f-d72d-528c-8d46-f43bb15c3842" },
  { "email": "owner@alpha.test", "role": "owner", "document_count": 0, "principal_id": "d5380d4a-796a-5bd3-ae7f-d881cd3dc98a" },
  { "email": "viewer@alpha.test", "role": "viewer", "document_count": 0, "principal_id": "c0960c69-f52f-5fc6-ba96-7e54495b1c11" }
]
```

`GET http://localhost:8000/admin/users` also **200**, 7 emails, identical set.

### See documents

```
GET http://localhost:8000/admin/members/0c9b84d9-5621-554a-b5ef-e52d5e7358c8/documents
status 200
[
  { "document_id": "c36cacf2-23a3-4cb8-9ae1-98650edb5253", "title": "Q3 Strategy Document", "source_type": "gdrive", "access_override": null },
  { "document_id": "3e7eb94f-75e3-4560-9cbc-0758c17bb2fb", "title": "Engineering Handbook", "source_type": "confluence", "access_override": null },
  { "document_id": "5115c93b-7bbe-4ee4-8713-82f3e316681b", "title": "Meeting Notes - Architecture Review", "source_type": "slack", "access_override": null }
]
```

### Deny

```
POST http://localhost:8000/admin/members/0c9b84d9-5621-554a-b5ef-e52d5e7358c8/documents/c36cacf2-23a3-4cb8-9ae1-98650edb5253/access
status 200
{ "message": "Access override set successfully" }
```

Follow-up GET of that member’s documents showed `"access_override": "deny"` on Q3 Strategy Document.

### Remove override

```
DELETE http://localhost:8000/admin/members/0c9b84d9-5621-554a-b5ef-e52d5e7358c8/documents/c36cacf2-23a3-4cb8-9ae1-98650edb5253/access
status 200
{ "message": "Access override removed successfully" }
```

Follow-up GET showed `"access_override": null` on all three documents.

---

## 6. Click path for you (independent check)

The frontend that was walked through is **production** `npm start` at **http://localhost:3000**, not `npm run dev`. Backend is Docker `snyq_app` on port 8000.

1. Open **http://localhost:3000/login**. (Production build does not show the yellow local-credentials hint.)
2. Email **admin@synq.dev**, password **AlphaAdmin123!**. Workspace is inferred as **alpha**.
3. You should land on **http://localhost:3000/admin**.
4. Skip or glance at "Organization Google Workspace" (Not connected is expected here). Directly under it is **Members**.
5. You should see seven rows with a document count and a blue **See documents** on the right. You should **not** need to scroll through Audit or Pending identities to find that.
6. Click **See documents** on **Alpha Member · member@alpha.test** (3 documents).
7. You should see three titles and a Default / Allow / Deny control on each.
8. Set **Q3 Strategy Document** to **Deny**. The red **Denied by admin** label should appear. DevTools → Network: `POST .../access` 200.
9. Set it back to **Default**. Label returns to **Default ACL**. Network: `DELETE .../access` 200.

If sign-in shows **Token has expired** before you even get a session: that was leftover `synq-auth` in localStorage. Clear site data for localhost:3000, or use a fresh browser profile. `getMe` was patched in source so a new production build does not prefer the dead stored token over the token login just issued.

---

## 7. Still incomplete / not claimed

- **Search enforcement of deny was not re-checked in this browser session.** Deny and remove were proven on the admin UI and on the override HTTP API. Whether a subsequent search hides Q3 Strategy Document for `member@alpha.test` was not walked through here.
- **"Documents assigned to" is owned documents only.** The backend lists `canonical_documents` where `owner_principal_id` equals the member. It is not "every document that member can read via ACL." If the product meaning of "assigned" is the larger ACL set, that list is still not built.
- **`connector_connected` is always false** in `document_access.py` (explicit TODO). The UI no longer depends on that badge for the required flow.
- **Alpha Admin’s 298 documents were not expanded** in this session (the list is scrollable inside the row; it would be a long list). The expand/Allow/Deny path was proven on the 3-document member.
- **Organization Google Workspace remains Not connected** on this account. Unrelated to member document access; not fixed here.
- Prior files `ui_screenshots/04_member_list.png` (Users list, no counts) and automated-walkthrough shots of the old buried section are **not** evidence for this session. Use the `2026-09-02_admin_*.png` files above.
