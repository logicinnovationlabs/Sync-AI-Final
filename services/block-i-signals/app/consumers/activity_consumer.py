"""Kafka / Event Hub consumer for ingest.activity.v1."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from app.config import settings
from app.models.activity import ActivityEvent
from app.services.factory import get_activity_store

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None


async def handle_activity_message(payload: Dict[str, Any]) -> str:
    """Process a single activity event dict from the bus."""
    store = get_activity_store()
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise ValueError("tenant_id required on bus event")
    event = ActivityEvent.model_validate(payload)
    return await store.ingest_event(tenant_id, event)


async def _consume_loop() -> None:
    """
    Lightweight consumer using aiokafka when available and kafka_enabled=true.

    Falls back to no-op if the dependency or broker is unavailable.
    """
    if not settings.kafka_enabled:
        return
    try:
        from aiokafka import AIOKafkaConsumer
    except ImportError:
        logger.warning("aiokafka not installed; activity consumer disabled")
        return

    consumer = AIOKafkaConsumer(
        settings.kafka_topic_activity,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        enable_auto_commit=True,
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    await consumer.start()
    logger.info(
        "Activity consumer started topic=%s group=%s",
        settings.kafka_topic_activity,
        settings.kafka_consumer_group,
    )
    try:
        async for msg in consumer:
            try:
                await handle_activity_message(msg.value)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to process activity message offset=%s", msg.offset)
    finally:
        await consumer.stop()


def start_activity_consumer() -> None:
    global _task
    if not settings.kafka_enabled or settings.environment == "test":
        return
    if _task is None or _task.done():
        _task = asyncio.create_task(_consume_loop(), name="block-i-activity-consumer")


async def stop_activity_consumer() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None


# Allow tests / Block B mock to push events without Kafka
async def publish_test_event(payload: Dict[str, Any]) -> str:
    return await handle_activity_message(payload)
