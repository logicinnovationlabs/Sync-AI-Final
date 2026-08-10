"""Factory for embedding providers from environment."""

from __future__ import annotations

import os

from app.embeddings.provider import EmbeddingProvider


def create_embedding_provider() -> EmbeddingProvider:
    provider = (os.environ.get("EMBEDDING_PROVIDER") or "mock").strip().lower()
    if provider in ("mock", "fake"):
        from app.embeddings.mock_provider import MockEmbeddingProvider
        dim = int(os.environ.get("EMBEDDING_DIMENSION") or os.environ.get("EMBEDDING_DIMENSIONS") or "1536")
        return MockEmbeddingProvider(vector_dimension=dim)
    if provider in ("gemini", "google", "google-gemini"):
        from app.embeddings.gemini_provider import GeminiEmbeddingProvider, gemini_config_from_env
        return GeminiEmbeddingProvider(gemini_config_from_env())
    if provider in ("azure", "azure-openai", "openai"):
        from app.embeddings.azure_provider import AzureOpenAIProvider, AzureOpenAIConfig
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        deployment = (
            os.environ.get("AZURE_OPENAI_DEPLOYMENT")
            or os.environ.get("EMBEDDING_MODEL")
            or "text-embedding-3-large"
        )
        if not endpoint or not api_key:
            raise RuntimeError("Azure OpenAI credentials missing")
        return AzureOpenAIProvider(
            AzureOpenAIConfig(endpoint=endpoint, api_key=api_key, deployment_name=deployment)
        )
    raise RuntimeError(f"Unknown EMBEDDING_PROVIDER={provider!r}")
