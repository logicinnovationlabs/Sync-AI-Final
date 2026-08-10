"""Retention purge job — deletes events past TTL and rebuilds aggregates."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.config import settings
from app.services.factory import get_activity_store

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None
_stop = asyncio.Event()


async def run_purge_once() -> dict:
    store = get_activity_store()
    result = await store.purge_expired()
    logger.info(
        "Retention purge: purged=%s tenants=%s",
        result.purged_events,
        result.tenants_touched,
    )
    return result.model_dump()


async def _loop() -> None:
    interval = max(5, int(settings.retention_job_interval_seconds))
    while not _stop.is_set():
        try:
            await run_purge_once()
        except Exception:  # noqa: BLE001
            logger.exception("Retention purge failed")
        try:
            await asyncio.wait_for(_stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


def start_retention_job() -> None:
    global _task
    if settings.environment == "test":
        return
    _stop.clear()
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(), name="block-i-retention")
        logger.info("Retention job started (interval=%ss)", settings.retention_job_interval_seconds)


async def stop_retention_job() -> None:
    global _task
    _stop.set()
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
