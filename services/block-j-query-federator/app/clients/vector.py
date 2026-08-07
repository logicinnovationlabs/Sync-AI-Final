"""Async HTTP client for Block G vector search."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class VectorClient:
    """Fan-out client for POST /api/v1/search/vector."""

    def __init__(self, client: httpx.AsyncClient, base_url: Optional[str] = None) -> None:
        self._client = client
        self.base_url = (base_url or settings.vector_search_url).rstrip("/")

    async def search(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        acl_terms: List[str],
        query_embedding: List[float],
        top_k: int = 50,
        model_version: Optional[str] = None,
        authorization: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call Block G vector search.

        Returns a dict with keys: results, model_versions_used, latency_ms.
        """
        payload: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "principal_id": principal_id,
            "acl_terms": acl_terms,
            "query_embedding": query_embedding,
            "top_k": top_k,
        }
        if model_version:
            payload["model_version"] = model_version

        headers = {}
        if authorization:
            headers["Authorization"] = authorization

        started = time.perf_counter()
        response = await self._client.post(
            f"{self.base_url}/api/v1/search/vector",
            json=payload,
            headers=headers,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        response.raise_for_status()
        data = response.json()
        data["latency_ms"] = latency_ms
        return data
