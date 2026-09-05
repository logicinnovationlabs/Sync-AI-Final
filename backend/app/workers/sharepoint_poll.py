"""Periodic SharePoint/OneDrive delta: enqueue incremental backfill per connected scope."""

from __future__ import annotations

import logging
from typing import Callable, Iterable, List, Tuple

logger = logging.getLogger(__name__)


def split_cursor_scope(scope_id: str) -> Tuple[str, str]:
    raw = str(scope_id or "").strip()
    if ":" in raw:
        tenant_id, user_id = raw.split(":", 1)
        return tenant_id, user_id
    return raw, ""


def acquire_poll_lock(tenant_id: str, user_id: str, ttl_seconds: int = 180) -> bool:
    try:
        from app.storage.redis_client import create_sync_redis_client

        client = create_sync_redis_client()
        if client is None:
            return True
        key = f"sharepoint_poll_lock:{tenant_id}:{user_id or 'personal'}"
        return bool(client.set(key, "1", nx=True, ex=ttl_seconds))
    except Exception:
        logger.warning("SharePoint poll lock unavailable tenant=%s", tenant_id)
        return True


def enqueue_sharepoint_delta_poll(
    scope_ids: Iterable[str],
    *,
    is_syncing: Callable[[str, str], bool],
    delay: Callable[..., object],
    acquire_lock: Callable[[str, str], bool] = acquire_poll_lock,
) -> dict:
    enqueued: List[str] = []
    skipped: List[str] = []
    for scope in scope_ids:
        tenant_id, user_id = split_cursor_scope(scope)
        if not tenant_id:
            skipped.append(str(scope))
            continue
        if is_syncing(tenant_id, user_id):
            skipped.append(str(scope))
            continue
        if not acquire_lock(tenant_id, user_id):
            skipped.append(str(scope))
            continue
        delay(tenant_id=tenant_id, source_type="sharepoint", user_id=user_id)
        enqueued.append(str(scope))
    return {"enqueued": len(enqueued), "skipped": len(skipped), "tenants": enqueued}
