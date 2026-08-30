"""Runtime connector status (active / syncing / error / needs_reauth)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

STATUSES = ("not_connected", "syncing", "active", "error", "needs_reauth")


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


def _key(tenant_id: str, source_type: str, user_id: str = "") -> str:
    uid = str(user_id or "").strip()
    if uid:
        return f"connector_status:{tenant_id}:{uid}:{source_type}"
    return f"connector_status:{tenant_id}:{source_type}"


def get_status_raw(
    tenant_id: str, source_type: str, user_id: str = ""
) -> Optional[Dict[str, Any]]:
    """Return stored status, or None when the Redis key is missing."""
    client = _sync_redis()
    if client is None:
        return None
    try:
        raw = client.get(_key(tenant_id, source_type, user_id))
        if not raw:
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        data.setdefault("connection_status", "not_connected")
        data.setdefault("files_indexed", 0)
        return data
    except Exception:
        return None


def get_status(tenant_id: str, source_type: str, user_id: str = "") -> Dict[str, Any]:
    empty = {
        "connection_status": "not_connected",
        "files_indexed": 0,
        "last_sync_at": None,
        "last_error": None,
    }
    data = get_status_raw(tenant_id, source_type, user_id=user_id)
    return data if data is not None else empty


def is_disconnected(tenant_id: str, source_type: str, user_id: str = "") -> bool:
    """True only when Redis explicitly records ``not_connected`` (after disconnect)."""
    data = get_status_raw(tenant_id, source_type, user_id=user_id)
    if data is None:
        return False
    return str(data.get("connection_status") or "") == "not_connected"


def clear_status(tenant_id: str, source_type: str, user_id: str = "") -> Dict[str, Any]:
    """Mark disconnected and keep the key so GET cannot re-infer Syncing from leftover tokens."""
    current = {
        "connection_status": "not_connected",
        "files_indexed": 0,
        "last_sync_at": None,
        "last_error": None,
    }
    client = _sync_redis()
    if client is not None:
        try:
            client.set(_key(tenant_id, source_type, user_id), json.dumps(current))
        except Exception as exc:
            logger.warning("Failed to clear connector status: %s", type(exc).__name__)
    return current


def set_status(
    tenant_id: str,
    source_type: str,
    *,
    user_id: str = "",
    connection_status: Optional[str] = None,
    files_indexed: Optional[int] = None,
    last_error: Optional[str] = None,
    increment_indexed: int = 0,
    force: bool = False,
) -> Dict[str, Any]:
    # Never let an in-flight backfill resurrect a disconnected connector.
    if (
        not force
        and is_disconnected(tenant_id, source_type, user_id=user_id)
        and connection_status != "not_connected"
    ):
        logger.info(
            "Skipping status update; connector disconnected tenant=%s source=%s user=%s",
            tenant_id,
            source_type,
            user_id,
        )
        return get_status(tenant_id, source_type, user_id=user_id)

    current = get_status(tenant_id, source_type, user_id=user_id)
    if connection_status:
        current["connection_status"] = connection_status
    if files_indexed is not None:
        current["files_indexed"] = int(files_indexed)
    elif increment_indexed:
        current["files_indexed"] = int(current.get("files_indexed") or 0) + increment_indexed
    if last_error is not None:
        current["last_error"] = last_error
    if connection_status in ("active", "error", "needs_reauth"):
        current["last_sync_at"] = datetime.now(timezone.utc).isoformat()
    client = _sync_redis()
    if client is not None:
        try:
            client.set(_key(tenant_id, source_type, user_id), json.dumps(current))
        except Exception as exc:
            logger.warning("Failed to persist connector status: %s", type(exc).__name__)
    return current
