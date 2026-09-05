# Auth Revocation Bypass Fix - Documentation

## Executive Summary

This fix addresses a P0 security vulnerability where deactivation, role changes, and session revocation did not properly invalidate existing JWT tokens. The issue affected multiple token issuance paths and allowed revoked users to continue accessing the system.

## Root Causes Identified

1. **Deactivation doesn't revoke**: `deactivate_user` and `patch_user` set flags but never bumped `token_version` or called `revocation_service.revoke_session`
2. **Refresh path ignores account state**: `refresh_access_token` never checked `is_active`/`status`, only re-derived scopes
3. **Refresh-issued tokens structurally unrevokable**: `issue_access_token` only stamped `token_version` when `role is not None`; refresh and OAuth flows passed `role=None`
4. **validate_token fails open**: Missing `token_version` claim was silently skipped instead of rejected

## Changes Made

### 1. Shared Revocation Function (`app/services/revocation.py`)

Added `revoke_user()` function that:
- Increments `token_version` on the user object
- Publishes new version to Redis (before DB commit for low latency)
- Calls `revoke_session()` to invalidate refresh tokens
- Returns new version for audit/logging

This is now the single source of truth for user revocation.

### 2. Admin User Management (`app/api/v1/admin/users.py`)

- **`patch_user`**: Now calls `revoke_user()` when `role` or `is_active` changes
- **`deactivate_user`**: Now calls `revoke_user()` before committing

Both paths use the shared revocation logic, eliminating drift.

### 3. OAuth Service (`app/services/oauth_service.py`)

- **`_scopes_for_principal`**: Now returns tuple of (scopes, user_metadata) and checks `is_active`/`status`
- **`exchange_authorization_code`**: Passes `role`, `token_version`, `must_change_password` to `issue_access_token`
- **`refresh_access_token`**: Passes user metadata to `issue_access_token`, rejects inactive users
- **`issue_tokens_for_client_credentials`**: Uses explicit `role="service"` and `token_version=0`

### 4. Token Service (`app/services/token_service.py`)

- **`issue_access_token`**: Always stamps `token_version` claim (removed `role is not None` guard)
- **`validate_token`**: Rejects tokens missing `token_version` claim (fails closed)
- **`rotate_refresh_token`**: Passes `token_version` from payload to new access token

## Refresh Token Family Decision

### Current State
- Refresh tokens are stored in `RefreshToken` table with `revoked` flag
- Each refresh has a unique `jti` that gets added to Redis revoked set on use
- No refresh token "family" or version concept exists

### Analysis
The current design already handles refresh token revocation adequately:
1. When a user is revoked, `revoke_session()` marks all their refresh tokens as revoked in DB
2. Each refresh token's `jti` is added to Redis revoked set when used
3. Refresh tokens have expiry time (TTL from settings)

### Decision: DEFERRED
Adding a refresh token family/version concept is **not required** for this P0 fix because:

1. **Access token revocation is the critical path**: The primary vulnerability was that access tokens (especially refresh-derived ones) lacked version checking. This is now fixed.
2. **Refresh tokens are already invalidated**: The existing `revoke_session()` logic marks refresh tokens as revoked in the DB and checks this on every refresh attempt.
3. **Refresh token rotation provides security**: The OAuth service rotates refresh tokens on every use, limiting the window of exposure.
4. **Complexity vs benefit**: A full refresh token family system would require schema changes, migration, and additional complexity for marginal security benefit.

### Future Enhancement (Optional)
If desired in the future, a refresh token family could be implemented by:
- Adding `refresh_family_id` and `family_version` columns to `RefreshToken` table
- Storing the active family version in Redis alongside `token_version`
- Checking both on refresh attempts
- This would allow revoking all refresh tokens in a family without individual DB updates

For now, the current design is sufficient for the P0 security requirement.

## Verification

### Unit Tests
Created comprehensive test suite in `tests/test_p0_auth_revocation.py` covering:
1. Deactivation blocks refresh attempts
2. Deactivation invalidates existing access tokens
3. Role downgrade invalidates old-scope tokens
4. Normal flows still work (regression tests)
5. Token version always stamped
6. Missing token_version rejected
7. Concurrent version bumps

### Real-Infra Verification Required
Before marking this complete, the following must be verified against the running auth service:

1. **Deactivation flow**: 
   - Create active user via admin panel
   - Login and obtain refresh token
   - Deactivate user via admin panel
   - Attempt refresh → should fail with 401/403

2. **Role change flow**:
   - Create admin user
   - Login and obtain admin-scoped token
   - Downgrade to member via admin panel
   - Old admin token should be rejected on next API call

3. **OAuth flows**:
   - Test authorization_code flow with deactivated user
   - Test client_credentials flow still works
   - Verify all issued tokens have `token_version` claim

4. **Legacy token rejection**:
   - Manually craft a JWT without `token_version`
   - Attempt to use it → should be rejected

## Multi-Tenant Safety

The fix respects tenant boundaries:
- `token_version` is stored per-tenant in Redis: `token_version:{principal_id}` under tenant partition
- Revocation operations are scoped to `tenant_id`
- No cross-tenant version collision possible

## Backward Compatibility

### Breaking Changes
- Tokens without `token_version` claim will be rejected (this is intentional for security)
- Existing refresh tokens for deactivated users will be rejected on next use

### Migration Notes
- No database schema changes required
- Redis keys will be created automatically on first revocation
- Existing valid tokens will continue to work until natural expiry or revocation

## Performance Impact

Minimal:
- One additional Redis GET per token validation (already existed, now mandatory)
- One additional Redis SET per revocation (already existed in sessions endpoint)
- No additional DB queries (user state already fetched in refresh path)

## Security Posture After Fix

1. **Deactivation is immediate**: Revoked users cannot refresh or use existing tokens
2. **Role changes propagate**: Old-scope tokens are rejected immediately
3. **Single revocation path**: No drift between different revocation mechanisms
4. **Fail-closed validation**: Missing claims are rejected, not silently ignored
5. **All issuance paths covered**: OAuth, native login, and service accounts all stamp version

## Related Issues Fixed

- Password change now also needs session revocation (separate but related gap identified)
- SCIM sync should call `revoke_user()` when deprovisioning users (future enhancement)
