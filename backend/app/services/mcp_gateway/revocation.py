"""MCP session cache + Redis revocation_events subscriber (M4).

Per-tenant cache, 30–60 min ceiling (uses tenant_cache_ttl_seconds, default 1800).
Pub/sub invalidation is the fast path. Does not poll /oauth/introspect.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional, Set

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

CHANNEL = "revocation_events"


class McpSessionCache:
    """Per-tenant identity cache plus revocation sets."""

    def __init__(self, ttl_seconds: int = 1800) -> None:
        self.ttl_seconds = ttl_seconds
        # tenant -> jti -> (principal_id, cached_at)
        self._entries: Dict[str, Dict[str, tuple[str, float]]] = {}
        self._revoked_jtis: Dict[str, Set[str]] = {}
        self._revoked_principals: Dict[str, Set[str]] = {}

    def remember(self, tenant_id: str, *, jti: str, principal_id: str) -> None:
        if not jti:
            return
        now = time.monotonic()
        bucket = self._entries.setdefault(tenant_id, {})
        bucket[jti] = (principal_id, now)

    def is_revoked(
        self,
        tenant_id: str,
        *,
        jti: str,
        principal_id: str,
    ) -> bool:
        self._expire(tenant_id)
        if jti and jti in self._revoked_jtis.get(tenant_id, set()):
            return True
        if principal_id and principal_id in self._revoked_principals.get(tenant_id, set()):
            return True
        return False

    def apply_event(self, payload: Dict[str, Any]) -> None:
        event_type = str(payload.get("event_type") or "")
        tenant_id = str(payload.get("tenant_id") or "")
        if not tenant_id:
            return
        if event_type == "token_revoked":
            jti = str(payload.get("jti") or "")
            if jti:
                self._revoked_jtis.setdefault(tenant_id, set()).add(jti)
                self._entries.get(tenant_id, {}).pop(jti, None)
        elif event_type == "session_revoked":
            principal_id = str(payload.get("principal_id") or "")
            if principal_id:
                self._revoked_principals.setdefault(tenant_id, set()).add(principal_id)
                bucket = self._entries.get(tenant_id, {})
                for jti, (pid, _) in list(bucket.items()):
                    if pid == principal_id:
                        bucket.pop(jti, None)

    def _expire(self, tenant_id: str) -> None:
        now = time.monotonic()
        bucket = self._entries.get(tenant_id, {})
        for jti, (_, cached_at) in list(bucket.items()):
            if now - cached_at > self.ttl_seconds:
                bucket.pop(jti, None)


mcp_session_cache = McpSessionCache(ttl_seconds=int(settings.tenant_cache_ttl_seconds))


class McpRevocationListener:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._client: Optional[aioredis.Redis] = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="mcp-revocation-listener")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    async def _run(self) -> None:
        try:
            client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=1.0,
            )
            await client.ping()
            self._client = client
        except Exception:
            logger.warning("MCP revocation listener: Redis unavailable, cache-only mode")
            return
        pubsub = client.pubsub()
        await pubsub.subscribe(CHANNEL)
        logger.info("MCP revocation listener subscribed to %s", CHANNEL)
        try:
            while not self._stop.is_set():
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message or message.get("type") != "message":
                    continue
                data = message.get("data")
                if not data:
                    continue
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                mcp_session_cache.apply_event(payload)
        finally:
            try:
                await pubsub.unsubscribe(CHANNEL)
                await pubsub.aclose()
            except Exception:
                pass


mcp_revocation_listener = McpRevocationListener()
