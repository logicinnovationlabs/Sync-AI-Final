"""Query embedding client (mock or remote API)."""

from __future__ import annotations

import hashlib
import logging
import math
from typing import List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Produce query embeddings for Block G fan-out."""

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        backend: Optional[str] = None,
        dimensions: Optional[int] = None,
    ) -> None:
        self._client = client
        self.backend = (backend or settings.embedding_backend).lower()
        self.dimensions = dimensions or settings.embedding_dimensions

    async def embed(self, text: str) -> List[float]:
        """Return an L2-normalized embedding for ``text``."""
        if self.backend == "openai":
            return await self._embed_openai(text)
        return self._embed_mock(text)

    def _embed_mock(self, text: str) -> List[float]:
        """Deterministic hash-based embedding (no network / model download)."""
        digest = hashlib.sha256(text.lower().encode("utf-8")).digest()
        values: List[float] = []
        # Expand digest material to fill dimensions
        seed = digest
        while len(values) < self.dimensions:
            for b in seed:
                # Map byte to [-1, 1]
                values.append((b / 127.5) - 1.0)
                if len(values) >= self.dimensions:
                    break
            seed = hashlib.sha256(seed).digest()

        # Mix in token hashes so overlapping query terms share signal
        for token in text.lower().split():
            th = hashlib.md5(token.encode("utf-8")).digest()
            for i, b in enumerate(th):
                idx = i % self.dimensions
                values[idx] += ((b / 255.0) - 0.5) * 0.25

        return _l2_normalize(values[: self.dimensions])

    async def _embed_openai(self, text: str) -> List[float]:
        if not self._client:
            raise RuntimeError("httpx client required for openai embedding backend")
        if not settings.embedding_api_url or not settings.embedding_api_key:
            raise RuntimeError("EMBEDDING_API_URL and EMBEDDING_API_KEY required")

        response = await self._client.post(
            settings.embedding_api_url,
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
            json={
                "input": text,
                "model": settings.embedding_model_version,
            },
        )
        response.raise_for_status()
        data = response.json()
        vector = data["data"][0]["embedding"]
        return _l2_normalize([float(x) for x in vector])


def _l2_normalize(vector: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]
