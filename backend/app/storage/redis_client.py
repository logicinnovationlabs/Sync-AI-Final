"""
Redis client with PER-TENANT cache partitioning.

Critical for Signoff A7: each tenant's cache must be isolated - never a shared cache.
Per Vishwas §28.2, we implement namespace-based partitioning: tenant:{tenant_id}:*
"""

from typing import Any, Optional
import json
import logging

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.exceptions import SnyQException

logger = logging.getLogger(__name__)


def normalized_redis_url(url: str) -> str:
    """Strip quotes and drop ssl_cert_reqs from the query string.

    redis-py only accepts query/kwarg values ``none`` / ``optional`` / ``required``.
    ``CERT_NONE`` (Celery/kombu style) raises Invalid SSL Certificate Requirements.
    Celery broker URLs can keep ``?ssl_cert_reqs=CERT_NONE``; this client uses
    ``ssl_cert_reqs=\"none\"`` via kwargs instead.
    """
    cleaned = (url or "").strip().strip('"').strip("'")
    if not cleaned or "ssl_cert_reqs" not in cleaned.lower():
        return cleaned
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

    parsed = urlparse(cleaned)
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() != "ssl_cert_reqs"
    ]
    return urlunparse(parsed._replace(query=urlencode(query)))


def redis_from_url_kwargs(
    url: str,
    *,
    decode_responses: bool = True,
    socket_connect_timeout: float = 8,
    socket_timeout: float = 8,
) -> dict:
    """Shared from_url kwargs for async + sync Redis (Upstash rediss://)."""
    kwargs: dict = {
        "decode_responses": decode_responses,
        "socket_connect_timeout": socket_connect_timeout,
        "socket_timeout": socket_timeout,
        "health_check_interval": 30,
    }
    if url.lower().startswith("rediss://"):
        # String "none" — not ssl.CERT_NONE. Passing the enum breaks redis-py:
        # RedisSSLContext object has no attribute 'cert_reqs'.
        kwargs["ssl_cert_reqs"] = "none"
        kwargs["ssl_check_hostname"] = False
    return kwargs


def create_sync_redis_client(url: str | None = None):
    """Sync Redis client for Google token/status stores (Celery + API)."""
    import redis as sync_redis

    resolved = normalized_redis_url(
        url
        or getattr(settings, "redis_url", None)
        or settings.session_store_redis_url
    )
    client = sync_redis.Redis.from_url(
        resolved, **redis_from_url_kwargs(resolved)
    )
    client.ping()
    return client


# Back-compat aliases used inside this module
_normalized_redis_url = normalized_redis_url


def _from_url_kwargs(url: str) -> dict:
    kwargs = redis_from_url_kwargs(url)
    kwargs["encoding"] = "utf-8"
    return kwargs


class TenantPartitionedRedisClient:
    """
    Redis client with mandatory per-tenant key partitioning.
    
    Every key is prefixed with tenant:{tenant_id}: to prevent cross-tenant leaks.
    This satisfies Vishwas §28.2 requirement that the tenant cache be partitioned.
    """

    def __init__(self, redis_url: str = settings.redis_url):
        self.redis_url = _normalized_redis_url(redis_url)
        self._client: Optional[aioredis.Redis] = None
        self._fallback_store: dict = {}
        self._fallback_sets: dict = {}

    async def connect(self):
        """Initialize Redis connection pool."""
        if self._client is not None:
            return
        url = _normalized_redis_url(self.redis_url or settings.redis_url)
        self.redis_url = url
        try:
            client = aioredis.from_url(url, **_from_url_kwargs(url))
            await client.ping()
            self._client = client
            logger.info("Redis ping ok")
        except Exception as exc:
            logger.warning("Redis connect failed (%s): %s", type(exc).__name__, exc)
            self._client = None

    async def disconnect(self):
        """Close Redis connection."""
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
        self._fallback_store.clear()
        self._fallback_sets.clear()

    def _make_key(self, tenant_id: str, key: str) -> str:
        """
        Build a partitioned key: tenant:{tenant_id}:{key}
        
        This ensures per-tenant isolation at the Redis level (A7).
        """
        return f"tenant:{tenant_id}:{key}"

    async def get(self, tenant_id: str, key: str) -> Optional[str]:
        """
        Get a value from the tenant's partition.
        """
        partitioned_key = self._make_key(tenant_id, key)
        if self._client is not None:
            try:
                return await self._client.get(partitioned_key)
            except Exception:
                pass
        return self._fallback_store.get(partitioned_key)

    async def set(
        self,
        tenant_id: str,
        key: str,
        value: str,
        ex: Optional[int] = None,
    ) -> None:
        """
        Set a value in the tenant's partition.
        """
        partitioned_key = self._make_key(tenant_id, key)
        if self._client is not None:
            try:
                await self._client.set(partitioned_key, value, ex=ex)
                return
            except Exception:
                pass
        self._fallback_store[partitioned_key] = str(value)

    async def delete(self, tenant_id: str, key: str) -> None:
        """
        Delete a key from the tenant's partition.
        """
        partitioned_key = self._make_key(tenant_id, key)
        if self._client is not None:
            try:
                await self._client.delete(partitioned_key)
                return
            except Exception:
                pass
        self._fallback_store.pop(partitioned_key, None)
        self._fallback_sets.pop(partitioned_key, None)

    async def get_json(self, tenant_id: str, key: str) -> Optional[Any]:
        """
        Get a JSON-deserialized value from the tenant's partition.
        """
        value = await self.get(tenant_id, key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    async def set_json(
        self,
        tenant_id: str,
        key: str,
        value: Any,
        ex: Optional[int] = None,
    ) -> None:
        """
        Set a JSON-serialized value in the tenant's partition.
        """
        serialized = json.dumps(value)
        await self.set(tenant_id, key, serialized, ex=ex)

    async def sadd(self, tenant_id: str, key: str, *members: str) -> int:
        """
        Add members to a set in the tenant's partition.
        """
        partitioned_key = self._make_key(tenant_id, key)
        if self._client is not None:
            try:
                return await self._client.sadd(partitioned_key, *members)
            except Exception:
                pass
        if partitioned_key not in self._fallback_sets:
            self._fallback_sets[partitioned_key] = set()
        added = 0
        for member in members:
            if member not in self._fallback_sets[partitioned_key]:
                self._fallback_sets[partitioned_key].add(member)
                added += 1
        return added

    async def sismember(self, tenant_id: str, key: str, member: str) -> bool:
        """
        Check if a member exists in a set.
        """
        partitioned_key = self._make_key(tenant_id, key)
        if self._client is not None:
            try:
                return await self._client.sismember(partitioned_key, member)
            except Exception:
                pass
        return member in self._fallback_sets.get(partitioned_key, set())

    async def publish(self, channel: str, message: str) -> None:
        """
        Publish a message to a Redis pub/sub channel.
        """
        if self._client is not None:
            try:
                await self._client.publish(channel, message)
            except Exception:
                pass


# Global Redis client instance
redis_client = TenantPartitionedRedisClient()

