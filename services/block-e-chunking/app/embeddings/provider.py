"""
Embedding Provider Interface
Abstract base class for embedding provider implementations.
Per Master Build Prompt v1.0, §5.1
"""

from abc import ABC, abstractmethod
from typing import List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class EmbeddingResult:
    """Result from embedding a single text."""
    vector: List[float]
    model_version: str
    generated_at: datetime
    token_count: int = 0


class EmbeddingProviderError(Exception):
    """Base exception for embedding provider errors."""
    pass


class EmbeddingProvider(ABC):
    """
    Abstract interface for embedding providers.
    
    All implementations must:
    - Support batched calls for throughput
    - Raise EmbeddingProviderError on failure (not bare exceptions)
    - Tag every call with tenant_id in metadata where provider supports it
    - Never batch chunks from more than one tenant per API call
    """
    
    @abstractmethod
    async def embed_batch(
        self,
        texts: List[str],
        tenant_id: str,
        model_version: str,
    ) -> List[EmbeddingResult]:
        """
        Returns one EmbeddingResult per input text, in order.
        
        Args:
            texts: List of text strings to embed
            tenant_id: Tenant identifier for isolation and metadata
            model_version: Model version string to stamp on results
        
        Returns:
            List of EmbeddingResult, one per input text, in same order
        
        Raises:
            EmbeddingProviderError: On any failure (rate limit, API error, etc.)
        """
        pass
    
    @abstractmethod
    def get_vector_dimension(self, model_version: str) -> int:
        """
        Returns the dimensionality of vectors produced by the given model version.
        
        Args:
            model_version: Model version string
        
        Returns:
            Integer dimension of the embedding vectors
        """
        pass
