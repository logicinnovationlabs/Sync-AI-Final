"""Best-effort event bus producer for ingest topics.

Kafka/Redpanda when a client library and broker are available; otherwise Redis
list + in-process handlers so the unified backend can still run auto-sync.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_handlers: List[Callable[[str, Dict[str, Any]], None]] = []
_kafka = None
_kafka_failed = False
_redis = None
_redis_failed = False


def register_handler(handler: Callable[[str, Dict[str, Any]], None]) -> None:
    _handlers.append(handler)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, default=str).encode("utf-8")


def _kafka_producer():
    global _kafka, _kafka_failed
    if _kafka_failed:
        return None
    if _kafka is not None:
        return _kafka
    brokers = getattr(settings, "kafka_brokers", None) or ""
    if not brokers:
        _kafka_failed = True
        return None
    try:
        from kafka import KafkaProducer  # type: ignore
    except Exception:
        _kafka_failed = True
        return None
    try:
        _kafka = KafkaProducer(
            bootstrap_servers=[b.strip() for b in brokers.split(",") if b.strip()],
            value_serializer=lambda v: _json_bytes(v) if not isinstance(v, (bytes, bytearray)) else v,
            request_timeout_ms=2000,
            api_version_auto_timeout_ms=2000,
        )
        return _kafka
    except Exception as exc:
        logger.warning("event_bus kafka unavailable (%s)", type(exc).__name__)
        _kafka_failed = True
        return None


def _redis_client():
    global _redis, _redis_failed
    if _redis_failed:
        return None
    if _redis is not None:
        return _redis
    try:
        import redis

        url = getattr(settings, "redis_url", None) or getattr(settings, "session_store_redis_url", None)
        client = redis.Redis.from_url(
            url, decode_responses=False, socket_connect_timeout=1.5, socket_timeout=1.5
        )
        client.ping()
        _redis = client
        return _redis
    except Exception as exc:
        logger.warning("event_bus redis unavailable (%s)", type(exc).__name__)
        _redis_failed = True
        return None


class _Producer:
    def send(self, topic: str, value: Dict[str, Any], key: Optional[str] = None) -> None:
        delivered = False
        producer = _kafka_producer()
        if producer is not None:
            try:
                kwargs: Dict[str, Any] = {"value": value}
                if key:
                    kwargs["key"] = key.encode("utf-8") if isinstance(key, str) else key
                producer.send(topic, **kwargs)
                producer.flush(timeout=2)
                delivered = True
            except Exception as exc:
                logger.warning("event_bus kafka send failed topic=%s (%s)", topic, type(exc).__name__)

        client = _redis_client()
        if client is not None:
            try:
                client.rpush(f"eventbus:{topic}", _json_bytes(value))
                delivered = True
            except Exception as exc:
                logger.warning("event_bus redis send failed topic=%s (%s)", topic, type(exc).__name__)

        for handler in list(_handlers):
            try:
                handler(topic, value)
                delivered = True
            except Exception as exc:
                logger.warning("event_bus handler failed topic=%s (%s)", topic, type(exc).__name__)

        if delivered:
            logger.info("event_bus published topic=%s source=%s id=%s", topic, value.get("source_type"), value.get("source_object_id"))
        else:
            logger.warning("event_bus drop topic=%s (no kafka/redis/handler)", topic)


producer = _Producer()
