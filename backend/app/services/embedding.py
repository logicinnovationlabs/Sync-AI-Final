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
    """
    Gemini-based embedding provider.
    
    Uses Google's Gemini embedding model via the genai SDK.
    """
    
    def __init__(self, api_key: str, model: str = "gemini-embedding-001", dimension: int = 3072):
        """
        Initialize Gemini provider.
        
        Args:
            api_key: Gemini API key
            model: Model name
            dimension: Embedding dimension
        """
        self.api_key = api_key
        self.model = _normalize_gemini_model_name(model)
        self.dimension = int(dimension)

        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self.genai = genai
    
    async def embed_texts(self, texts: List[str], *, task_type: Optional[str] = None) -> List[List[float]]:
        """Generate embeddings sequentially in small batches with 429 backoff."""
        if not texts:
            return []

        import asyncio

        batch_size = max(1, int(getattr(settings, "embedding_batch_size", None) or 8))

        def _is_quota(err: Exception) -> bool:
            s = str(err).lower()
            return (
                "429" in s
                or "quota" in s
                or "resourceexhausted" in s
                or "resource exhausted" in s
            )

        async def _call(kwargs: dict) -> List[List[float]]:
            result = await asyncio.to_thread(self.genai.embed_content, **kwargs)
            embs = result.get("embedding", [])
            if embs and isinstance(embs[0], (int, float)):
                return [embs]
            return embs

        async def _embed_with_retry(kwargs: dict, what: str) -> List[List[float]]:
            last_exc: Optional[Exception] = None
            for attempt in range(6):
                try:
                    return await _call(kwargs)
                except Exception as e:
                    last_exc = e
                    if _is_quota(e) and attempt < 5:
                        wait_sec = min(90, 5 * (2 ** attempt))
                        logger.warning(
                            "Embedding rate limited (%s), retrying in %ss: %s",
                            what,
                            wait_sec,
                            e,
                        )
                        await asyncio.sleep(wait_sec)
                        continue
                    raise
            raise last_exc  # pragma: no cover

        embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            truncated_batch = [t[:8000] for t in batch]
            kwargs = {
                "model": self.model,
                "content": truncated_batch,
                "output_dimensionality": self.dimension,
            }
            if task_type:
                kwargs["task_type"] = task_type
            try:
                embeddings.extend(await _embed_with_retry(kwargs, "batch"))
            except Exception as e:
                logger.warning(
                    "Batch embedding failed (%s), falling back to sequential single calls",
                    e,
                )
                for t in truncated_batch:
                    one_kw = {
                        "model": self.model,
                        "content": t,
                        "output_dimensionality": self.dimension,
                    }
                    if task_type:
                        one_kw["task_type"] = task_type
                    embeddings.extend(await _embed_with_retry(one_kw, "single"))
        return embeddings

    def get_dimension(self) -> int:
        return self.dimension


class FakeEmbeddingProvider:
    """
    Fake/deterministic embedding provider for tests and development.
    
    Generates consistent embeddings based on text hash.
    """
    
    def __init__(self, dimension: int = 3072):
        """
        Initialize fake provider.
        
        Args:
            dimension: Embedding dimension
        """
        self.dimension = dimension
    
    async def embed_texts(self, texts: List[str], *, task_type: Optional[str] = None) -> List[List[float]]:
        """
        Generate deterministic fake embeddings.
        
        Uses text hash to generate consistent vectors.
        
        Args:
            texts: List of text strings
            task_type: Optional task type for Phase 1 compatibility
            
        Returns:
            List of embedding vectors
        """
        prefix = f"{task_type or 'none'}::"
        embeddings = []
        for text in texts:
            text_hash = hashlib.sha256((prefix + text).encode()).hexdigest()
            vector: List[float] = []
            for i in range(self.dimension):
                byte_idx = (i * 2) % len(text_hash)
                hex_val = int(text_hash[byte_idx : byte_idx + 2], 16)
                vector.append((hex_val / 128.0) - 1.0)
            embeddings.append(vector)
        return embeddings

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
            # Prefer EMBEDDING_DIMENSIONS (plural, QdrantVectorStore) so a leftover
            # EMBEDDING_DIMENSION=768 cannot silently undersize vectors vs the
            # live 3072-d `documents` collection.
            dimension = (
                getattr(settings, "embedding_dimensions", None)
                or 3072
            )
            
            if not api_key:
                raise ValueError("GEMINI_API_KEY not configured")
            self.provider = GeminiEmbeddingProvider(api_key, model, dimension)
        elif provider_name == "fake":
            dimension = (
                getattr(settings, "embedding_dimensions", None)
                or 3072
            )
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
