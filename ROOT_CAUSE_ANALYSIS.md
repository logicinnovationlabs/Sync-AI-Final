# Root Cause Analysis: Indexing vs. Querying Disconnect

## Issue Summary
Documents are being indexed from Google Drive and OneDrive (showing "5 indexed"), but when users ask questions, the system responds with "I don't have that information in the available documents" even though the documents are present.

## Root Cause

**ACL (Access Control List) Mismatch Between Indexing and Querying**

### The Problem

When documents are indexed (during sync/backfill), the ACL terms are generated using the `_acl_terms_for_user()` function in `backend/app/workers/tasks.py` (line 1170-1178):

```python
def _acl_terms_for_user(user_id: Optional[str]) -> list:
    principal = str(user_id or "")
    if not principal:
        return []
    terms = [principal]
    if not principal.startswith(("user:", "group:")):
        terms.append(f"user:{principal}")
    return terms
```

**This function generates only 2 ACL term formats:**
1. `principal` (bare, e.g., `"user-uuid-123"`)
2. `user:principal` (prefixed, e.g., `"user:user-uuid-123"`)

However, when querying (during search), the ACL terms are extracted from the JWT using `acl_terms_from_jwt()` in `backend/app/acl/filter.py` (line 87-127):

```python
def acl_terms_from_jwt(payload: Mapping[str, Any]) -> List[str]:
    # Extracts:
    # 1. principal (bare)
    # 2. user:principal (prefixed)
    # 3. email (bare, lowercased)
    # 4. user:email (prefixed, lowercased)
    # 5. groups (bare and prefixed)
```

**This function generates up to 5+ ACL term formats including:**
1. `principal` (bare)
2. `user:principal` (prefixed)
3. `email@example.com` (bare email, lowercased)
4. `user:email@example.com` (prefixed email, lowercased)
5. Group memberships (if any)

### The Mismatch

**Scenario:**
- User's `principal_id` in JWT: `"550e8400-e29b-41d4-a716-446655440000"`
- User's `email` in JWT: `"john@company.com"`
- User's `mailbox_email` from Google/Microsoft OAuth: `"john@company.com"`

**During Indexing:**
Documents get ACL terms: `["550e8400-e29b-41d4-a716-446655440000", "user:550e8400-e29b-41d4-a716-446655440000"]`

**During Querying:**
The search uses ACL terms from JWT: `["550e8400-e29b-41d4-a716-446655440000", "user:550e8400-e29b-41d4-a716-446655440000", "john@company.com", "user:john@company.com"]`

**Result:**
- If the documents were indexed with only the UUID-based terms and the JWT now includes email-based terms
- Or if the mailbox_email wasn't properly included during indexing
- **The ACL filter won't match and documents won't be returned**

### Additional Issues

1. **Incomplete Email Handling**: Line 519 in `tasks.py` attempts to add mailbox_email to ACL terms:
   ```python
   if mailbox_email:
       owner_acl = list(dict.fromkeys(owner_acl + _acl_terms_for_user(f"user:{mailbox_email}")))
   ```
   But passing `"user:mailbox@example.com"` to `_acl_terms_for_user` results in only:
   - `"user:mailbox@example.com"` (already prefixed, so no double prefix)
   
   Missing: `"mailbox@example.com"` (bare, lowercased)

2. **No Email Normalization**: The indexing doesn't lowercase emails, but querying does.

3. **Missing Group Support**: Groups from JWT aren't being added during indexing.

## Impact

- **100% query failure** when ACL terms don't match
- Documents appear indexed in status (correct)
- But search returns 0 results (ACL filtered out)
- System shows "I don't have that information" even with valid documents

## Solution Required

1. **Unify ACL term generation** - Create a single function that matches `acl_terms_from_jwt` logic
2. **Include all identity formats** - principal_id, user:principal_id, email (lowercase), user:email (lowercase)
3. **Normalize emails** - Always lowercase during both indexing and querying
4. **Reindex existing documents** - Trigger reindexing with corrected ACL terms

## Files to Fix

1. `backend/app/workers/tasks.py` - Update `_acl_terms_for_user` function
2. `backend/app/services/indexer.py` - Ensure consistent ACL term generation
3. `backend/app/acl/filter.py` - Potentially extract common ACL generation logic
4. Add reindexing endpoint/task to fix already-indexed documents
