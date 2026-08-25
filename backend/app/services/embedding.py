"""
Embedding service - generates vector embeddings for documents.

Matches Phase 1 SynQ behavior:
- Gemini ``gemini-embedding-001`` with explicit ``output_dimensionality``
- ``task_type=retrieval_document`` when indexing passages
- ``task_type=retrieval_query`` when embedding the user question
"""

from __future__ import annotations

import hashlib
import logging
from typing import List, Optional, Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

TASK_RETRIEVAL_DOCUMENT = "retrieval_document"
TASK_RETRIEVAL_QUERY = "retrieval_query"


def _normalize_gemini_model_name(model: str | None) -> str:
    """google-generativeai requires models/ or tunedModels/ prefix."""
    name = (model or "").strip() or "gemini-embedding-001"
    if name.startswith("models/") or name.startswith("tunedModels/"):
        return name
    return f"models/{name}"


class EmbeddingProvider(Protocol):
    async def embed_texts(
        self,
        texts: List[str],
        *,
        task_type: Optional[str] = None,
    ) -> List[List[float]]:
        ...

    def get_dimension(self) -> int:
        ...


class GeminiEmbeddingProvider:
    """Gemini embeddings via google-generativeai (Phase 1 compatible)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-001",
        dimension: int = 3072,
    ):
        self.api_key = api_key
        self.model = _normalize_gemini_model_name(model)
        self.dimension = int(dimension)

        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self.genai = genai

    def _fit_dimension(self, vector: List[float]) -> List[float]:
        if len(vector) == self.dimension:
            return vector
        if len(vector) > self.dimension:
            logger.warning(
                "Fitting Gemini vector %s → %s (prefer EMBEDDING_DIMENSION=3072 like Phase 1)",
                len(vector),
                self.dimension,
            )
            return vector[: self.dimension]
        return vector + [0.0] * (self.dimension - len(vector))

    def _embed_one(self, text: str, task_type: Optional[str]) -> List[float]:
        model = _normalize_gemini_model_name(self.model)
        truncated = (text or "")[:10000]
        kwargs = {
            "model": model,
            "content": truncated,
            "output_dimensionality": int(self.dimension),
        }
        if task_type:
            kwargs["task_type"] = task_type

        try:
            result = self.genai.embed_content(**kwargs)
        except TypeError:
            fallback = {"model": model, "content": truncated}
            if task_type:
                fallback["task_type"] = task_type
            try:
                result = self.genai.embed_content(**fallback)
            except TypeError:
                result = self.genai.embed_content(model=model, content=truncated)

        raw = result.get("embedding") if isinstance(result, dict) else None
        if raw is None:
            raw = getattr(result, "embedding", None) or []
        return self._fit_dimension(list(raw))

    async def embed_texts(
        self,
        texts: List[str],
        *,
        task_type: Optional[str] = None,
    ) -> List[List[float]]:
        return [self._embed_one(text, task_type) for text in texts]

    def get_dimension(self) -> int:
        return self.dimension


class FakeEmbeddingProvider:
    """Deterministic hash embeddings for offline tests."""

    def __init__(self, dimension: int = 3072):
        self.dimension = int(dimension)

    async def embed_texts(
        self,
        texts: List[str],
        *,
        task_type: Optional[str] = None,
    ) -> List[List[float]]:
        prefix = f"{task_type or 'none'}::"
        out: List[List[float]] = []
        for text in texts:
            text_hash = hashlib.sha256((prefix + text).encode()).hexdigest()
            vector: List[float] = []
            for i in range(self.dimension):
                byte_idx = (i * 2) % len(text_hash)
                hex_val = int(text_hash[byte_idx : byte_idx + 2], 16)
                vector.append((hex_val / 128.0) - 1.0)
            out.append(vector)
        return out

    def get_dimension(self) -> int:
        return self.dimension


class EmbeddingService:
    """Facade selecting Gemini or fake from settings."""

    def __init__(self) -> None:
        provider_name = (
            getattr(settings, "embedding_provider", None)
            or getattr(settings, "EMBEDDING_PROVIDER", "fake")
            or "fake"
        )
        provider_name = str(provider_name).strip().lower()

        dimension = int(
            getattr(settings, "embedding_dimension", None)
            or getattr(settings, "embedding_dimensions", None)
            or getattr(settings, "EMBEDDING_DIMENSION", None)
            or getattr(settings, "EMBEDDING_DIMENSIONS", None)
            or 3072
        )

        if provider_name == "gemini":
            api_key = (
                getattr(settings, "gemini_api_key", None)
                or getattr(settings, "GEMINI_API_KEY", "")
            )
            model = (
                getattr(settings, "embedding_model", None)
                or getattr(settings, "model_version", None)
                or getattr(settings, "EMBEDDING_MODEL", None)
                or getattr(settings, "MODEL_VERSION", None)
                or "gemini-embedding-001"
            )
            if not api_key:
                raise ValueError("GEMINI_API_KEY not configured")
            self.provider = GeminiEmbeddingProvider(api_key, model, dimension)
        elif provider_name == "fake":
            self.provider = FakeEmbeddingProvider(dimension)
        else:
            raise ValueError(f"Unknown embedding provider: {provider_name!r}")

    async def embed_texts(
        self,
        texts: List[str],
        *,
        task_type: Optional[str] = None,
    ) -> List[List[float]]:
        if not texts:
            return []
        return await self.provider.embed_texts(texts, task_type=task_type)

    async def embed_text(
        self,
        text: str,
        *,
        task_type: Optional[str] = None,
    ) -> List[float]:
        vectors = await self.embed_texts([text], task_type=task_type)
        return vectors[0] if vectors else []

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Index-time passage embeddings (Phase 1 retrieval_document)."""
        return await self.embed_texts(texts, task_type=TASK_RETRIEVAL_DOCUMENT)

    async def embed_query(self, text: str) -> List[float]:
        """Query-time embedding (Phase 1 retrieval_query)."""
        return await self.embed_text(text, task_type=TASK_RETRIEVAL_QUERY)

    def get_dimension(self) -> int:
        return self.provider.get_dimension()


embedding_service = EmbeddingService()
