"""Optional event handlers for ingest.canonical.v1."""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.consumers.canonical_consumer import CanonicalConsumer

logger = logging.getLogger(__name__)


async def handle_canonical_event(event: Dict[str, Any]) -> None:
    """Entry point for Kafka / bus adapters."""
    consumer = CanonicalConsumer()
    await consumer.process_event(event)
