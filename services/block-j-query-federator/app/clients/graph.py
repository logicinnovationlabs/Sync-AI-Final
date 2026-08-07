"""Async HTTP client for Block H graph signals."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class GraphClient:
    """
    Client for graph ranking signals (collaboration / ownership boosts).

    Prefers POST /graph/signals; falls back to empty signals on 404 so
    real Block H deployments without the signals route still degrade cleanly.
    """

    def __init__(self, client: httpx.AsyncClient, base_url: Optional[str] = None) -> None:
        self._client = client
        self.base_url = (base_url or settings.graph_service_url).rstrip("/")

    async def fetch_signals(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        document_ids: List[str],
        authorization: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch per-document graph boosts.

        Returns:
            {
              "signals": {doc_id: {"total_boost": float, ...}},
              "latency_ms": float,
            }
        """
        if not document_ids:
            return {"signals": {}, "latency_ms": 0.0}

        headers = {}
        if authorization:
            headers["Authorization"] = authorization

        payload = {
            "tenant_id": tenant_id,
            "principal_id": principal_id,
            "document_ids": document_ids,
        }

        started = time.perf_counter()
        response = await self._client.post(
            f"{self.base_url}/graph/signals",
            json=payload,
            headers=headers,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0

        if response.status_code == 404:
            logger.info("Graph signals endpoint missing; returning empty signals")
            return {"signals": {}, "latency_ms": latency_ms}

        response.raise_for_status()
        data = response.json()
        data["latency_ms"] = latency_ms
        return data
