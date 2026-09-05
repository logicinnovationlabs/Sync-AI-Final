"""OAuth state parameter: HMAC-signed + session-bound + CSRF nonce.

SECURITY DESIGN:
- State is HMAC-SHA256 signed to prevent tampering
- State is bound to initiating user's JWT jti (session binding)
- Nonce stored in Redis with jti for validation
- FAILS CLOSED on Redis errors (rejects request)
- tenant_id/user_id in state are advisory only, never trusted for privileged ops
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from typing import Any, Dict, Optional
from urllib.parse import quote

import base64

from app.core.config import settings

logger = logging.getLogger(__name__)

_STATE_TTL_SECONDS = 600
_REDIS_PREFIX = "google_oauth_state"
_HMAC_ALGORITHM = "sha256"


_REDIS = None
_REDIS_INIT = False


def _get_hmac_secret() -> str:
    """Get HMAC secret from settings. Falls back to TOKEN_ENCRYPTION_KEY if needed."""
    # Try to get a dedicated OAuth state secret first
    secret = getattr(settings, "oauth_state_secret", None) or ""
    if not secret:
        # Fall back to TOKEN_ENCRYPTION_KEY (used for token encryption)
        secret = getattr(settings, "token_encryption_key", None) or ""
    if not secret:
        # Last resort: use JWT secret (not ideal but better than nothing)
        logger.warning("No dedicated OAuth state secret configured, using fallback")
        secret = "default-oauth-state-secret-change-in-production"
    return str(secret)


def _sync_redis():
    global _REDIS, _REDIS_INIT
    if _REDIS_INIT:
        return _REDIS
    _REDIS_INIT = True
    try:
        from app.storage.redis_client import create_sync_redis_client

        _REDIS = create_sync_redis_client()
        return _REDIS
    except Exception:
        _REDIS = None
        return None


def encode_oauth_state(tenant_id: str, user_id: str, connection_scope: str = "personal", jti: str = "", binding_token: str = "") -> str:
    """
    Build a HMAC-signed, session-bound state string.

    SECURITY:
    - State is HMAC-SHA256 signed to prevent tampering
    - State is bound to initiating user's JWT jti (session binding)
    - State is bound to cookie-based binding_token (prevents URL forwarding)
    - Nonce stored in Redis with jti and binding_token for callback validation
    - tenant_id/user_id are advisory only (for UX), never trusted for privileged ops

    Args:
        tenant_id: Tenant UUID (advisory only, for UX)
        user_id: User principal UUID (advisory only, for UX)
        connection_scope: "personal" or "organization"
        jti: JWT token ID from authenticated request (CRITICAL for session binding)
        binding_token: Cookie-based binding token (CRITICAL for preventing URL forwarding)

    Returns:
        Base64url-encoded state with HMAC signature
    """
    nonce = secrets.token_urlsafe(24)
    payload = {
        "tenant_id": str(tenant_id),  # Advisory only - never trust for privileged ops
        "user_id": str(user_id),      # Advisory only - never trust for privileged ops
        "nonce": nonce,
        "connection_scope": connection_scope,
        "jti": jti,  # CRITICAL: binds state to initiating session
        "binding_token": binding_token,  # CRITICAL: binds state to cookie (prevents URL forwarding)
    }

    # Store nonce + jti + binding_token in Redis for callback validation
    client = _sync_redis()
    if client is not None:
        try:
            # Store with nonce as key, value includes jti and binding_token for session binding
            state_data = {
                "nonce": nonce,
                "jti": jti,
                "binding_token": binding_token,
                "connection_scope": connection_scope,
            }
            client.setex(f"{_REDIS_PREFIX}:{nonce}", _STATE_TTL_SECONDS, json.dumps(state_data))
        except Exception as exc:
            logger.error("Failed to persist OAuth state nonce: %s", type(exc).__name__)
            # FAILS CLOSED: if we can't store nonce, we can't safely issue state
            raise RuntimeError("OAuth state storage failed - cannot safely issue authorization URL") from exc
    else:
        logger.error("Redis client unavailable - cannot safely issue OAuth state")
        raise RuntimeError("Redis unavailable - cannot safely issue OAuth state")

    # Sign the payload with HMAC
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    secret = _get_hmac_secret().encode("utf-8")
    signature = hmac.new(secret, raw, hashlib.sha256).digest()
    
    # Combine payload + signature and encode
    combined = raw + b"." + base64.urlsafe_b64encode(signature)
    return base64.urlsafe_b64encode(combined).decode("ascii").rstrip("=")


def decode_oauth_state(state: str, require_jti_match: Optional[str] = None, require_binding_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Decode and validate state with HMAC verification and session binding.

    SECURITY:
    - Verifies HMAC signature to prevent tampering
    - Validates nonce exists in Redis (replay protection)
    - Optionally validates jti matches current session (session binding)
    - Optionally validates binding_token matches cookie (prevents URL forwarding)
    - FAILS CLOSED on any Redis error or signature failure
    - Returns None on any validation failure

    Args:
        state: Base64url-encoded state with HMAC signature
        require_jti_match: If provided, state's jti must match this value (session binding)
        require_binding_token: If provided, state's binding_token must match this value (cookie binding)

    Returns:
        Payload dict if valid, None if invalid/tampered/replayed
    """
    if not state:
        logger.warning("OAuth state is empty")
        return None

    padded = state + ("=" * ((4 - len(state) % 4) % 4))
    try:
        combined = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception:
        logger.warning("OAuth state base64 decode failed")
        return None

    # Split payload and signature
    if b"." not in combined:
        logger.warning("OAuth state missing signature separator")
        return None

    try:
        raw, sig_b64 = combined.split(b".", 1)
        signature = base64.urlsafe_b64decode(sig_b64)
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        logger.warning("OAuth state payload decode failed")
        return None

    # Verify HMAC signature
    secret = _get_hmac_secret().encode("utf-8")
    expected_sig = hmac.new(secret, raw, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_sig):
        logger.warning("OAuth state HMAC signature verification failed")
        return None

    # Extract required fields
    nonce = payload.get("nonce")
    if not nonce:
        logger.warning("OAuth state missing nonce")
        return None

    # Validate nonce in Redis (FAILS CLOSED)
    client = _sync_redis()
    if client is None:
        logger.error("Redis unavailable - cannot validate OAuth state nonce")
        return None  # FAILS CLOSED

    try:
        stored = client.get(f"{_REDIS_PREFIX}:{nonce}")
        if not stored:
            logger.warning("OAuth state nonce missing or expired")
            return None

        stored_data = json.loads(stored)

        # Validate jti match if required (session binding)
        if require_jti_match is not None:
            stored_jti = stored_data.get("jti", "")
            if stored_jti != require_jti_match:
                logger.warning("OAuth state jti mismatch - session binding failed")
                return None

        # Validate binding_token match if required (cookie binding - prevents URL forwarding)
        if require_binding_token is not None:
            stored_binding_token = stored_data.get("binding_token", "")
            if not hmac.compare_digest(stored_binding_token, require_binding_token):
                logger.warning("OAuth state binding_token mismatch - cookie binding failed (URL forwarding attack blocked)")
                return None

        # Delete nonce to prevent replay (one-time use)
        client.delete(f"{_REDIS_PREFIX}:{nonce}")
    except json.JSONDecodeError:
        logger.warning("OAuth state stored data JSON decode failed")
        return None
    except Exception as exc:
        logger.error("OAuth state Redis validation failed: %s", type(exc).__name__)
        return None  # FAILS CLOSED
    
    return payload


def frontend_connectors_redirect(status: str, error: Optional[str] = None) -> str:
    """Redirect URL after Google OAuth callback."""
    base = (
        getattr(settings, "frontend_url", None)
        or "http://localhost:3000"
    ).rstrip("/")
    url = f"{base}/connectors?google={quote(status)}"
    if error:
        url += f"&error={quote(error)}"
    return url
