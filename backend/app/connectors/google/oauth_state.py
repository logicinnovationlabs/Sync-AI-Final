"""OAuth state parameter: CSRF nonce + tenant_id + user_id (base64url JSON)."""

from __future__ import annotations

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


_REDIS = None
_REDIS_INIT = False


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


def encode_oauth_state(tenant_id: str, user_id: str, connection_scope: str = "personal") -> str:
    """
    Build a CSRF-protected state string carrying tenant_id and user_id.

    A random nonce is stored in Redis and embedded in the payload so the
    callback can reject replays / forged states.

    Args:
        tenant_id: Tenant UUID
        user_id: User principal UUID
        connection_scope: "personal" or "organization"
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
        return payload

    try:
        stored = client.get(f"{_REDIS_PREFIX}:{nonce}")
        if not stored:
            logger.warning("OAuth state nonce missing or expired")
            return None
        client.delete(f"{_REDIS_PREFIX}:{nonce}")
    except Exception as exc:
        logger.warning("OAuth state Redis check failed: %s", type(exc).__name__)
        return payload

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
