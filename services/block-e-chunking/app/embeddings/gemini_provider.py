"""
Gemini Embedding Provider Adapter (Phase 2 interim)

Architecture section 6.2 assumes Azure OpenAI. Gemini is an explicit interim deviation
for Phase 2 E2 unblocking — see SIGNOFF.md Deviations.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from app.embeddings.provider import EmbeddingProvider, EmbeddingResult, EmbeddingProviderError


@dataclass
class GeminiConfig:
    api_key: str
    model: str = "gemini-embedding-001"
    output_dimensionality: int = 768
    max_retries: int = 5
    retry_delay_ms: int = 500
    max_batch_size: int = 100
    request_timeout_seconds: float = 60.0


def _l2_normalize(vec: List[float]) -> List[float]:
    """Required for gemini-embedding-001 when output_dimensionality != 3072."""
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Real Gemini embedding provider via Generative Language API."""

    def __init__(self, config: GeminiConfig):
        if not config.api_key:
            raise EmbeddingProviderError("GEMINI_API_KEY is required for GeminiEmbeddingProvider")
        self.config = config
        self.call_log: List[dict] = []
        self.throttle_events = 0
        self.total_api_calls = 0
        self.total_texts_embedded = 0
        self.last_batch_latency_ms = 0.0

    def get_vector_dimension(self, model_version: str) -> int:
        return int(self.config.output_dimensionality)

    def _endpoint(self, method: str) -> str:
        base = "https://generativelanguage.googleapis.com/v1beta"
        return f"{base}/models/{self.config.model}:{method}?key={self.config.api_key}"

    def _post_json(self, url: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.request_timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))

    async def _post_json_async(self, url: str, payload: dict) -> dict:
        return await asyncio.to_thread(self._post_json, url, payload)

    async def embed_batch(
        self,
        texts: List[str],
        tenant_id: str,
        model_version: str,
    ) -> List[EmbeddingResult]:
        if not texts:
            raise EmbeddingProviderError("Cannot embed empty text list")
        if not tenant_id:
            raise EmbeddingProviderError("tenant_id is required for embedding calls")
        if len(texts) > self.config.max_batch_size:
            raise EmbeddingProviderError(
                f"Batch size {len(texts)} exceeds max_batch_size {self.config.max_batch_size}"
            )

        self.call_log.append(
            {
                "tenant_id": tenant_id,
                "model_version": model_version,
                "batch_size": len(texts),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        started = time.perf_counter()
        try:
            vectors = await self._embed_batch_api(texts)
        except EmbeddingProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingProviderError(f"Gemini embed failed: {exc}") from exc
        self.last_batch_latency_ms = (time.perf_counter() - started) * 1000.0
        self.total_api_calls += 1
        self.total_texts_embedded += len(texts)

        now = datetime.now(timezone.utc)
        return [
            EmbeddingResult(
                vector=vec,
                model_version=model_version or self.config.model,
                generated_at=now,
                token_count=0,
            )
            for vec in vectors
        ]

    async def _embed_batch_api(self, texts: List[str]) -> List[List[float]]:
        requests = [
            {
                "model": f"models/{self.config.model}",
                "content": {"parts": [{"text": t[:8000]}]},
                "taskType": "RETRIEVAL_DOCUMENT",
                "outputDimensionality": self.config.output_dimensionality,
            }
            for t in texts
        ]
        payload = {"requests": requests}
        url = self._endpoint("batchEmbedContents")

        last_err: Optional[Exception] = None
        for attempt in range(self.config.max_retries):
            try:
                data = await self._post_json_async(url, payload)
                embeddings = data.get("embeddings") or []
                if len(embeddings) != len(texts):
                    raise EmbeddingProviderError(
                        f"Gemini returned {len(embeddings)} embeddings for {len(texts)} texts"
                    )
                out: List[List[float]] = []
                for emb in embeddings:
                    values = list(emb.get("values") or [])
                    if len(values) != self.config.output_dimensionality:
                        raise EmbeddingProviderError(
                            f"Expected dim {self.config.output_dimensionality}, got {len(values)}"
                        )
                    if self.config.output_dimensionality != 3072:
                        values = _l2_normalize(values)
                    out.append(values)
                return out
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                last_err = e
                if e.code in (429, 500, 503):
                    self.throttle_events += 1
                    delay = (self.config.retry_delay_ms / 1000.0) * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                raise EmbeddingProviderError(f"Gemini HTTP {e.code}: {body[:400]}") from e
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                delay = (self.config.retry_delay_ms / 1000.0) * (2 ** attempt)
                await asyncio.sleep(delay)

        raise EmbeddingProviderError(f"Gemini embed exhausted retries: {last_err}")


def gemini_config_from_env() -> GeminiConfig:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = (
        os.environ.get("EMBEDDING_MODEL")
        or os.environ.get("GEMINI_EMBEDDING_MODEL")
        or "gemini-embedding-001"
    ).strip()
    dim = int(
        os.environ.get("EMBEDDING_DIMENSION")
        or os.environ.get("EMBEDDING_DIMENSIONS")
        or "768"
    )
    return GeminiConfig(
        api_key=api_key,
        model=model,
        output_dimensionality=dim,
        max_batch_size=int(os.environ.get("GEMINI_MAX_BATCH_SIZE", "100")),
    )
