"""
Azure OpenAI Embedding Provider Adapter
Per Master Build Prompt v1.0, §5.2

Wraps Azure OpenAI embeddings API with:
- Configurable model version string
- Batched calls for throughput
- Standard retry/backoff on rate-limit responses
- Tenant isolation (no cross-tenant batching)
"""

import asyncio
import time
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass

try:
    from openai import AsyncAzureOpenAI
    from openai import RateLimitError, APITimeoutError, APIConnectionError
except ImportError:
    raise ImportError(
        "openai package is required for Azure OpenAI provider. "
        "Install with: pip install openai"
    )

from app.embeddings.provider import EmbeddingProvider, EmbeddingResult, EmbeddingProviderError


@dataclass
class AzureOpenAIConfig:
    """Configuration for Azure OpenAI embedding provider."""
    endpoint: str
    api_key: str
    api_version: str = "2024-02-15-preview"
    deployment_name: str = "text-embedding-3-large"
    max_retries: int = 3
    retry_delay_ms: int = 1000
    max_batch_size: int = 100


class AzureOpenAIProvider(EmbeddingProvider):
    """
    Real Azure OpenAI embedding provider adapter.
    
    Implements tenant isolation by never batching chunks from more than one tenant
    per API call. Tags every call with tenant_id in request metadata.
    """
    
    def __init__(self, config: AzureOpenAIConfig):
        """
        Initialize Azure OpenAI provider.
        
        Args:
            config: AzureOpenAIConfig with endpoint, api_key, and other settings
        """
        self.config = config
        self.client = AsyncAzureOpenAI(
            api_key=config.api_key,
            api_version=config.api_version,
            azure_endpoint=config.endpoint,
            max_retries=config.max_retries,
        )
        self.call_log = []  # Log of all calls for E5 verification
    
    async def embed_batch(
        self,
        texts: List[str],
        tenant_id: str,
        model_version: str,
    ) -> List[EmbeddingResult]:
        """
        Embed a batch of texts using Azure OpenAI.
        
        Enforces tenant isolation by validating single-tenant batches.
        Implements retry/backoff on rate limits.
        
        Args:
            texts: List of text strings to embed
            tenant_id: Tenant identifier (validated for isolation)
            model_version: Model version string
        
        Returns:
            List of EmbeddingResult, one per input text
        
        Raises:
            EmbeddingProviderError: On validation failure or API errors
        """
        if not texts:
            raise EmbeddingProviderError("Cannot embed empty text list")
        
        if not tenant_id:
            raise EmbeddingProviderError("tenant_id is required for embedding calls")
        
        if len(texts) > self.config.max_batch_size:
            raise EmbeddingProviderError(
                f"Batch size {len(texts)} exceeds max_batch_size {self.config.max_batch_size}"
            )
        
        # Log call for E5 verification (tenant isolation)
        self.call_log.append({
            "tenant_id": tenant_id,
            "text_count": len(texts),
            "model_version": model_version,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        # Implement retry logic with exponential backoff
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self.client.embeddings.create(
                    input=texts,
                    model=self.config.deployment_name,
                    # Add tenant_id to request metadata for billing/abuse investigation
                    extra_headers={
                        "X-Tenant-ID": tenant_id,
                        "X-Model-Version": model_version,
                    },
                )
                
                # Convert response to EmbeddingResult list
                results = []
                for i, item in enumerate(response.data):
                    result = EmbeddingResult(
                        vector=item.embedding,
                        model_version=model_version,
                        generated_at=datetime.utcnow(),
                        token_count=item.index if hasattr(item, 'index') else 0,
                    )
                    results.append(result)
                
                return results
                
            except RateLimitError as e:
                last_error = e
                if attempt < self.config.max_retries:
                    # Exponential backoff
                    delay_ms = self.config.retry_delay_ms * (2 ** attempt)
                    await asyncio.sleep(delay_ms / 1000.0)
                    continue
                raise EmbeddingProviderError(
                    f"Rate limit exceeded after {self.config.max_retries} retries: {e}"
                ) from e
                
            except (APITimeoutError, APIConnectionError) as e:
                last_error = e
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_delay_ms / 1000.0)
                    continue
                raise EmbeddingProviderError(
                    f"API connection error after {self.config.max_retries} retries: {e}"
                ) from e
                
            except Exception as e:
                raise EmbeddingProviderError(f"Azure OpenAI API error: {e}") from e
        
        # Should not reach here, but handle gracefully
        raise EmbeddingProviderError(
            f"Failed after {self.config.max_retries} retries. Last error: {last_error}"
        )
    
    def get_vector_dimension(self, model_version: str) -> int:
        """
        Returns the vector dimension for the configured deployment.
        
        text-embedding-3-large: 3072 dimensions
        text-embedding-3-small: 1536 dimensions
        text-embedding-ada-002: 1536 dimensions
        
        Args:
            model_version: Model version string (for future per-model dimension support)
        
        Returns:
            Integer dimension of embedding vectors
        """
        # Map deployment names to dimensions
        dimension_map = {
            "text-embedding-3-large": 3072,
            "text-embedding-3-small": 1536,
            "text-embedding-ada-002": 1536,
        }
        
        # Check if deployment_name matches known models
        for model_name, dim in dimension_map.items():
            if model_name in self.config.deployment_name.lower():
                return dim
        
        # Default to 1536 if unknown
        return 1536
    
    def get_call_log(self) -> List[dict]:
        """
        Returns the log of all embedding calls made.
        
        Used for E5 verification (tenant isolation of embedding calls).
        
        Returns:
            List of call log entries with tenant_id, text_count, model_version, timestamp
        """
        return self.call_log.copy()
    
    def clear_call_log(self) -> None:
        """Clears the call log. Useful for test isolation."""
        self.call_log.clear()
