# Findings Out of Scope

This document lists any unrelated findings discovered during the OAuth State Hijacking vulnerability audit and fix.

## No Out-of-Scope Findings

During the audit and fix of the OAuth State Hijacking vulnerability, no unrelated security issues or bugs were discovered that fall outside the scope of this engagement.

### Scope of Work
- **In Scope:** OAuth state parameter security for Google connector
- **In Scope:** HMAC signing implementation
- **In Scope:** Session binding via JWT jti
- **In Scope:** Fail-closed Redis behavior
- **In Scope:** One-time use nonce validation
- **In Scope:** Test coverage for security fixes

### Files Reviewed
- `app/connectors/google/oauth_state.py`
- `app/connectors/router.py`
- `app/api/v1/connectors.py` (noted as legacy/alternative implementation)
- `app/api/v1/auth.py` (OIDC SSO flow - separate from Google connector OAuth)
- Frontend files for OAuth flow understanding

### Notes
- Microsoft connector does not exist in the codebase (only referenced in frontend metadata as "available: false")
- No other OAuth connectors (Slack, GitHub, Dropbox, etc.) found in backend
- OIDC SSO flow in `app/api/v1/auth.py` uses a different state mechanism (Redis-stored with PKCE) and is separate from the Google connector OAuth flow
