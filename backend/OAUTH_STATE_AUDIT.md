# OAUTH STATE AUDIT - Phase 1 Findings

**Date:** 2026-08-29
**Severity:** C1 Critical
**Vulnerability:** OAuth State Hijacking / Cross-Tenant Token Theft
**Scope:** `connectors/google/authorize`, `connectors/google/callback`, `decode_oauth_state`

---

## EXECUTIVE SUMMARY

A critical account-takeover vulnerability exists in SynQ AI's OAuth connector flow. The state parameter is unsigned base64 JSON containing tenant_id and user_id, with no binding to the initiating session. The callback trusts these client-controlled values to determine where to store tokens, allowing an attacker to hijack a victim's OAuth authorization code and store the victim's tokens under the attacker's tenant.

**CRITICAL DEFECTS CONFIRMED:**
1. State is unsigned base64 JSON (no HMAC signature)
2. State is not bound to initiating session (only nonce in Redis)
3. `decode_oauth_state` FAILS OPEN on Redis errors (lines 90-92, 100-102)
4. Callback trusts tenant_id/user_id from client-controlled state
5. No Microsoft connector exists (only Google implemented)

---

## 1. STATE CONSTRUCTION LOCATIONS

### 1.1 Google OAuth State Construction

**File:** `app/connectors/google/oauth_state.py`
**Function:** `encode_oauth_state` (lines 40-67)

```python
def encode_oauth_state(tenant_id: str, user_id: str, connection_scope: str = "personal") -> str:
    """
    Build a CSRF-protected state string carrying tenant_id and user_id.

    A random nonce is stored in Redis and embedded in the payload so the
    callback can reject replays / forged states.
    """
    nonce = secrets.token_urlsafe(24)
    payload = {
        "tenant_id": str(tenant_id),
        "user_id": str(user_id),
        "nonce": nonce,
        "connection_scope": connection_scope,
    }
    client = _sync_redis()
    if client is not None:
        try:
            client.setex(f"{_REDIS_PREFIX}:{nonce}", _STATE_TTL_SECONDS, json.dumps(payload))
        except Exception as exc:
            logger.warning("Could not persist OAuth state nonce: %s", type(exc).__name__)

    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
```

**Fields in state payload:**
- `tenant_id`: Tenant UUID (from authenticated request)
- `user_id`: User principal UUID (from authenticated request)
- `nonce`: Random CSRF nonce (24 bytes, URL-safe base64)
- `connection_scope`: "personal" or "organization"

**Encoding method:** base64url (no padding), NO SIGNATURE, NO HMAC

**TTL:** 600 seconds (10 minutes) - line 17: `_STATE_TTL_SECONDS = 600`

**Redis key schema:** `google_oauth_state:{nonce}`

### 1.2 State Construction Callers

**File:** `app/connectors/router.py`
**Function:** `get_google_authorize_url` (lines 567-600)

```python
@router.get(
    "/google/authorize",
    summary="Generate Google OAuth authorization URL",
    dependencies=[Depends(require_scope("connectors.write"))],
)
async def get_google_authorize_url(
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != str(tenant_id):
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    client_id = settings.google_client_id or ""
    if not client_id:
        raise HTTPException(status_code=503, detail="GOOGLE_CLIENT_ID is not configured")

    redirect_uri = _google_redirect_uri()
    user_id = _user_id(current_user)
    state = encode_oauth_state(str(tenant_id), user_id, "personal")  # LINE 591
    token_store = PersistentGoogleTokenStore(str(tenant_id))
    oauth = google_oauth_from_settings(token_store, principal_id=user_id, connection_scope="personal")
    auth_url = oauth.build_authorization_url(str(tenant_id), redirect_uri, state=state)

    return {
        "authorization_url": auth_url,
        "tenant_id": tenant_id,
        "connection_scope": "personal",
    }
```

**Organization scope variant:** `get_google_authorize_url_organization` (lines 603-636)
- Line 627: `state = encode_oauth_state(str(tenant_id), user_id, "organization")`

### 1.3 Other OAuth Connectors

**Microsoft Connector:** NOT FOUND
- No Microsoft OAuth connector implementation exists in the codebase
- No `/connectors/microsoft/authorize` or `/connectors/microsoft/callback` endpoints
- No `app/connectors/microsoft/` directory

**Slack Connector:** NOT FOUND
- No Slack OAuth connector implementation exists

**Notion Connector:** NOT FOUND
- No Notion OAuth connector implementation exists

**Conclusion:** Only Google OAuth connector is implemented. The vulnerability exists only for Google.

---

## 2. DECODE_OAUTH_STATE FUNCTION

### 2.1 Function Location and Body

**File:** `app/connectors/google/oauth_state.py`
**Function:** `decode_oauth_state` (lines 70-104)

```python
def decode_oauth_state(state: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate state. Returns payload or None if invalid / replayed.
    """
    if not state:
        return None
    padded = state + ("=" * ((4 - len(state) % 4) % 4))
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None

    tenant_id = payload.get("tenant_id")
    user_id = payload.get("user_id")
    nonce = payload.get("nonce")
    if not tenant_id or not user_id or not nonce:
        return None

    client = _sync_redis()
    if client is None:
        # Dev/test without Redis: accept structurally valid state.
        return payload  # LINE 92 - FAILS OPEN

    try:
        stored = client.get(f"{_REDIS_PREFIX}:{nonce}")
        if not stored:
            logger.warning("OAuth state nonce missing or expired")
            return None
        client.delete(f"{_REDIS_PREFIX}:{nonce}")  # LINE 99 - One-time use
    except Exception as exc:
        logger.warning("OAuth state Redis check failed: %s", type(exc).__name__)
        return payload  # LINE 102 - FAILS OPEN

    return payload
```

### 2.2 FAILS OPEN Behavior Confirmed

**Line 90-92:** If Redis client is None (unavailable), function returns payload instead of None
```python
if client is None:
    # Dev/test without Redis: accept structurally valid state.
    return payload  # FAILS OPEN
```

**Line 100-102:** If Redis operation throws exception, function returns payload instead of None
```python
except Exception as exc:
    logger.warning("OAuth state Redis check failed: %s", type(exc).__name__)
    return payload  # FAILS OPEN
```

**Impact:** An attacker who can degrade Redis (or trigger transient Redis error) can skip the nonce check entirely.

### 2.3 Callers of decode_oauth_state

**File:** `app/connectors/router.py`
**Function:** `google_oauth_callback` (line 666)

```python
payload = decode_oauth_state(state)
if not payload:
    logger.error(f"OAuth callback invalid state: state={state}")
    return RedirectResponse(
        frontend_connectors_redirect("error", "invalid_state"),
        status_code=302,
    )
```

**Test file:** `tests/test_google_oauth_flow.py`
- Line 65: `decoded = decode_oauth_state(qs["state"][0])`
- Line 178: `decoded = decode_oauth_state(qs["state"][0])`

---

## 3. REDIS NONCE STORAGE MECHANISM

### 3.1 Nonce Storage at Authorize Time

**File:** `app/connectors/google/oauth_state.py`
**Lines 59-64**

```python
client = _sync_redis()
if client is not None:
    try:
        client.setex(f"{_REDIS_PREFIX}:{nonce}", _STATE_TTL_SECONDS, json.dumps(payload))
    except Exception as exc:
        logger.warning("Could not persist OAuth state nonce: %s", type(exc).__name__)
```

**Redis key schema:** `google_oauth_state:{nonce}`
**TTL:** 600 seconds (10 minutes)
**Value:** Full JSON payload (including tenant_id, user_id, nonce, connection_scope)

### 3.2 Nonce Lookup at Callback Time

**File:** `app/connectors/google/oauth_state.py`
**Lines 94-99**

```python
try:
    stored = client.get(f"{_REDIS_PREFIX}:{nonce}")
    if not stored:
        logger.warning("OAuth state nonce missing or expired")
        return None
    client.delete(f"{_REDIS_PREFIX}:{nonce}")  # One-time use
```

### 3.3 CRITICAL FINDING: No Session Binding

The nonce is stored in Redis with ONLY the nonce as the key. There is NO association with:
- The JWT `jti` of the user who called `/authorize`
- The session ID
- The principal_id from the authenticated request context
- Any server-side session identifier

**Redis key:** `google_oauth_state:{nonce}` (only nonce)
**Should be:** `google_oauth_state:{nonce}:{jti}` or similar to bind to initiating session

The nonce value contains the full payload (tenant_id, user_id, etc.), but this is client-controlled data embedded in the state, not server-side session data.

---

## 4. CALLBACK TRUST BOUNDARY ANALYSIS

### 4.1 Google Callback Trust Boundary

**File:** `app/connectors/router.py`
**Function:** `google_oauth_callback` (lines 639-734)

**Line 643-648:** Callback is UNAUTHENTICATED by design
```python
async def google_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """
    Unauthenticated by design: Google redirects the browser here without our JWT.
    Binding is the CSRF state nonce issued by /google/authorize.
    """
```

**Line 666:** Decode state from client-controlled query parameter
```python
payload = decode_oauth_state(state)
```

**Lines 674-676:** Extract tenant_id/user_id from CLIENT-CONTROLLED state
```python
tenant_id = str(payload["tenant_id"])
user_id = str(payload["user_id"])
connection_scope = str(payload.get("connection_scope") or "personal")
```

**Line 681:** Use client-controlled user_id for OAuth manager
```python
oauth = google_oauth_from_settings(token_store, principal_id=user_id, connection_scope=connection_scope)
```

**Line 683:** Exchange victim's code for tokens
```python
token_data = await oauth.exchange_code_for_tokens(tenant_id, code, redirect_uri)
```

**Line 696:** Store tokens under client-controlled tenant_id/user_id
```python
token_store.set_token(google_oauth_token_key(tenant_id, user_id, connection_scope), merged)
```

**Lines 704, 700:** Record connector rows using client-controlled values
```python
await _record_connector_rows(tenant_id, user_id, mailbox_email)
await _record_organization_connector_rows(tenant_id, user_id, mailbox_email)
```

**Lines 716-721:** Enqueue backfill using client-controlled values
```python
backfill_source.delay(
    tenant_id=tenant_id,
    source_type=source_type,
    user_id=runtime_user_id,
    connector_id=google_credential_ref(tenant_id, user_id, connection_scope),
)
```

### 4.2 Trust Boundary Violation Summary

**All privileged operations use tenant_id/user_id from client-controlled state:**
1. Token storage key: `google_oauth_token_key(tenant_id, user_id, connection_scope)`
2. Connector row creation: `tenant_id`, `user_id` from state
3. Backfill task enqueue: `tenant_id`, `user_id` from state
4. OAuth manager initialization: `principal_id=user_id` from state

**NO server-side session validation:**
- Callback does not require JWT authentication
- Callback does not validate session cookie
- Callback does not compare state values to any server-side record
- Callback trusts the state parameter as the sole source of truth for identity

---

## 5. CSRF/ORIGIN CONTROLS

### 5.1 CSRF Protection

**Existing CSRF protection:** Only the nonce in Redis
- Nonce is stored and checked to prevent replay attacks
- However, nonce is not bound to initiating session
- Attacker can obtain valid nonce by calling `/authorize` themselves

**No additional CSRF controls found:**
- No SameSite cookie attribute enforcement
- No CSRF token in cookies
- No double-submit cookie pattern
- No origin/referrer header validation

### 5.2 Origin Validation

**No origin validation found:**
- Callback does not validate `Origin` header
- Callback does not validate `Referer` header
- Callback does not validate `Host` header beyond FastAPI's built-in checks

**Comment in code (line 651):**
```python
"""
Unauthenticated by design: Google redirects the browser here without our JWT.
Binding is the CSRF state nonce issued by /google/authorize.
"""
```

This comment incorrectly claims the nonce provides binding, but the nonce is not bound to the initiating session.

### 5.3 Session Cookie Validation

**No session cookie validation:**
- Callback does not check for session cookie
- Callback does not validate session cookie against state
- Callback is explicitly unauthenticated (line 650)

---

## 6. GOOGLE VS MICROSOFT COMPARISON

### 6.1 Microsoft Connector Status

**Microsoft connector does not exist.**

Search results:
- No `app/connectors/microsoft/` directory
- No `/connectors/microsoft/authorize` endpoint
- No `/connectors/microsoft/callback` endpoint
- No Microsoft OAuth state functions
- No Microsoft token storage

### 6.2 Comparison Table

| Feature | Google | Microsoft |
|---------|--------|-----------|
| Connector exists | YES | NO |
| Authorize endpoint | `/connectors/google/authorize` | N/A |
| Callback endpoint | `/connectors/google/callback` | N/A |
| State construction | `encode_oauth_state` | N/A |
| State decoding | `decode_oauth_state` | N/A |
| Redis nonce storage | YES | N/A |
| FAILS OPEN on Redis error | YES | N/A |
| Unsigned state | YES | N/A |
| No session binding | YES | N/A |

**Conclusion:** Only Google connector is vulnerable. Microsoft connector does not exist and therefore cannot be fixed.

---

## 7. PROOF OF CONCEPT RESULTS

### 7.1 PoC Test File

**File:** `tests/test_oauth_state_hijacking_poc.py`

### 7.2 Test Results

```
tests/test_oauth_state_hijacking_poc.py::TestOAuthStateHijackingVulnerability::test_state_is_unsigned_base64_json PASSED
tests/test_oauth_state_hijacking_poc.py::TestOAuthStateHijackingVulnerability::test_decode_oauth_state_fails_open_on_redis_unavailable PASSED
tests/test_oauth_state_hijacking_poc.py::TestOAuthStateHijackingVulnerability::test_decode_oauth_state_fails_open_on_redis_exception PASSED
tests/test_oauth_state_hijacking_poc.py::TestOAuthStateHijackingVulnerability::test_cross_tenant_token_theft_scenario PASSED
tests/test_oauth_state_hijacking_poc.py::TestOAuthStateHijackingVulnerability::test_state_not_bound_to_initiating_session PASSED
tests/test_oauth_state_hijacking_poc.py::TestOAuthStateHijackingVulnerability::test_nonce_only_deleted_after_successful_use PASSED
```

All 6 tests PASSED, demonstrating the vulnerability exists.

### 7.3 Key Vulnerabilities Demonstrated

1. **test_state_is_unsigned_base64_json:** State can be forged by modifying tenant_id/user_id and re-encoding
2. **test_decode_oauth_state_fails_open_on_redis_unavailable:** Returns payload when Redis is None (line 92)
3. **test_decode_oauth_state_fails_open_on_redis_exception:** Returns payload when Redis throws exception (line 102)
4. **test_cross_tenant_token_theft_scenario:** Full attack scenario works - victim's code stored under attacker's tenant
5. **test_state_not_bound_to_initiating_session:** No binding to JWT jti or session ID
6. **test_nonce_only_deleted_after_successful_use:** Nonce deletion doesn't prevent the initial exploit

---

## 8. ATTACK SCENARIO WALKTHROUGH

### Step-by-Step Attack

1. **Attacker calls `/authorize`** (authenticated as attacker@tenant-a.com)
   - Receives state with `{"tenant_id": "tenant-a", "user_id": "attacker-user", "nonce": "..."}`
   - Nonce stored in Redis: `google_oauth_state:{nonce}`

2. **Attacker constructs Google OAuth URL** with attacker's state
   - URL: `https://accounts.google.com/o/oauth2/v2/auth?...&state={attacker_state}`

3. **Attacker sends URL to victim** (victim@tenant-b.com)
   - Via email, chat, or social engineering
   - URL looks legitimate (real Google consent screen for real SynQ OAuth client)

4. **Victim authenticates with Google**
   - Victim sees legitimate Google consent screen
   - Victim consents to Drive + Gmail access
   - Victim believes they're connecting their own account

5. **Google redirects to `/callback`**
   - Redirects with: `code={victim_code}&state={attacker_state}`
   - Victim's browser hits callback with attacker's state

6. **Callback decodes state** (line 666)
   - Extracts `tenant_id = "tenant-a"` (attacker's tenant)
   - Extracts `user_id = "attacker-user"` (attacker's user)

7. **Callback exchanges victim's code for tokens** (line 683)
   - Calls Google token endpoint with victim's code
   - Receives tokens for victim's Google account

8. **Callback stores tokens under attacker's tenant** (line 696)
   - Storage key: `google_oauth:tenant-a:attacker-user:personal`
   - Tokens belong to victim's Google account but stored under attacker's tenant

9. **Backfill enqueued for attacker's tenant** (lines 716-721)
   - Drive + Gmail backfill runs for tenant-a
   - Ingests victim's files and emails into attacker's tenant

10. **Attacker searches victim's data**
    - Attacker logs into SynQ as attacker@tenant-a.com
    - Searches for victim's emails, files, documents
    - Full access to victim's Drive + Gmail

### Why This Works

- State is unsigned - attacker can't forge it, but they CAN obtain a valid one
- State is not bound to session - anyone can use a valid state
- Callback trusts state values - uses tenant_id/user_id from state for all operations
- No server-side validation - callback doesn't check who initiated the flow

---

## 9. ROOT CAUSES SUMMARY

### 9.1 Technical Root Causes

1. **Unsigned state parameter**
   - No HMAC signature
   - No JWT signing
   - Client can read and modify (but not forge without valid nonce)

2. **No session binding**
   - Nonce not associated with initiating user's JWT jti
   - Nonce not associated with session ID
   - Anyone with valid nonce can complete the flow

3. **FAILS OPEN on Redis errors**
   - Lines 90-92: Returns payload when Redis is None
   - Lines 100-102: Returns payload when Redis throws exception
   - Attacker can bypass nonce check by degrading Redis

4. **Trust in client-controlled values**
   - Callback uses tenant_id/user_id from state for all privileged operations
   - No server-side identity validation
   - No comparison to authenticated session

5. **Unauthenticated callback**
   - Callback explicitly has no JWT requirement
   - No session cookie validation
   - Relies solely on state parameter for identity

### 9.2 Design Flaws

1. **OAuth callback design assumes state is trustworthy**
   - State is treated as source of truth for identity
   - Should only be advisory/display-only

2. **Nonce-only CSRF protection insufficient**
   - Nonce prevents replay but doesn't bind to session
   - Attacker can obtain valid nonce by calling authorize themselves

3. **No defense in depth**
   - Single point of failure (state validation)
   - No secondary checks (session, origin, etc.)

---

## 10. FINDINGS OUT OF SCOPE

No unrelated issues found during this audit. All findings are directly related to the OAuth state hijacking vulnerability.

---

## 11. FILES REQUIRING FIXES

### Primary Files
1. `app/connectors/google/oauth_state.py` - State encoding/decoding logic
2. `app/connectors/router.py` - Callback endpoint (lines 639-734)

### Secondary Files
3. `tests/test_google_oauth_flow.py` - Update tests to cover new security requirements
4. `tests/test_oauth_state_hijacking_poc.py` - PoC test (will be updated to verify fix)

### Files NOT requiring changes
- No Microsoft connector exists
- No other OAuth connectors exist
- Legacy API endpoint (`app/api/v1/connectors.py`) is deprecated/not in use

---

## 12. PHASE 1 CONCLUSION

**Vulnerability CONFIRMED.** All claims in the master prompt have been verified against the actual codebase:

✅ State is unsigned base64 JSON
✅ State is not bound to initiating session
✅ decode_oauth_state FAILS OPEN on Redis errors
✅ Callback trusts client-controlled tenant_id/user_id
✅ No Microsoft connector exists (only Google)
✅ PoC demonstrates the exploit successfully

**Next Phase:** Implement fixes in Phase 2.
