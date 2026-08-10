"""Async HTTP client for Block F lexical search."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LexicalClient:
    """Fan-out client for POST /search/lexical."""

    def __init__(self, client: httpx.AsyncClient, base_url: Optional[str] = None) -> None:
        self._client = client
        self.base_url = (base_url or settings.lexical_search_url).rstrip("/")

    async def search(
        self,
        *,
        query: str,
        tenant_id: str,
        user_id: str,
        acl_terms: List[str],
        filters: Optional[Dict[str, Any]] = None,
        facets: Optional[List[str]] = None,
        size: int = 50,
        from_: int = 0,
        authorization: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call Block F lexical search.

        Returns a dict with keys: results, facets, total, took_ms, latency_ms.
        Raises on transport / HTTP errors (caller handles degradation).
        """
        payload: Dict[str, Any] = {
            "query": query,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "acl_terms": acl_terms,
            "from": from_,
            "size": size,
        }
        if filters:
            payload["filters"] = filters
        if facets:
            payload["facets"] = facets

        headers = {}
        if authorization:
            headers["Authorization"] = authorization

        started = time.perf_counter()
        response = await self._client.post(
            f"{self.base_url}/search/lexical",
            json=payload,
            headers=headers,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        response.raise_for_status()
        data = response.json()
        data["latency_ms"] = latency_ms
        return data
