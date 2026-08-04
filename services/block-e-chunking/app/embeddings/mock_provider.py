"""
Latency-Simulated Mock Embedding Provider
Per Master Build Prompt v1.0, §5.3

This is NOT a stub that returns instantly. It simulates the actual latency profile
of a real embedding API call (tens-to-hundreds of milliseconds per call, configurable,
with jitter). Returns deterministic pseudo-random vectors of correct dimensionality.
"""

import asyncio
import hashlib
import random
import time
from typing import List
from datetime import datetime

from app.embeddings.provider import EmbeddingProvider, EmbeddingResult, EmbeddingProviderError


class MockEmbeddingProvider(EmbeddingProvider):
    """
    Latency-simulated mock embedding provider for Phase 1 signoff.
    
    Simulates realistic embedding API latency (tens-to-hundreds of ms per call)
    with configurable jitter. Returns deterministic pseudo-random vectors based on
    input text hash for reproducible test results.
    """
    
    def __init__(
        self,
        base_latency_ms: int = 100,
        jitter_ms: int = 50,
        vector_dimension: int = 1536,  # OpenAI text-embedding-3-large default
    ):
        """
        Initialize mock provider with latency configuration.
        
        Args:
            base_latency_ms: Base latency in milliseconds per batch
            jitter_ms: Random jitter to add/subtract from base latency
            vector_dimension: Dimension of embedding vectors to generate
        """
        self.base_latency_ms = base_latency_ms
        self.jitter_ms = jitter_ms
        self.vector_dimension = vector_dimension
        self.call_log = []  # Log of all calls for E5 verification (tenant isolation)
    
    async def embed_batch(
        self,
        texts: List[str],
        tenant_id: str,
        model_version: str,
    ) -> List[EmbeddingResult]:
        """
        Embed a batch of texts with simulated latency.
        
        Logs call composition for E5 tenant isolation verification.
        
        Args:
            texts: List of text strings to embed
            tenant_id: Tenant identifier
            model_version: Model version string
        
        Returns:
            List of EmbeddingResult, one per input text
        
        Raises:
            EmbeddingProviderError: If texts is empty or tenant_id is missing
        """
        if not texts:
            raise EmbeddingProviderError("Cannot embed empty text list")
        
        if not tenant_id:
            raise EmbeddingProviderError("tenant_id is required for embedding calls")
        
        # Log call for E5 verification (tenant isolation)
        self.call_log.append({
            "tenant_id": tenant_id,
            "text_count": len(texts),
            "model_version": model_version,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        # Simulate realistic latency with jitter
        latency = self.base_latency_ms + random.randint(-self.jitter_ms, self.jitter_ms)
        latency = max(0, latency)  # Ensure non-negative
        await asyncio.sleep(latency / 1000.0)
        
        # Generate deterministic pseudo-random vectors based on text hash
        results = []
        for text in texts:
            vector = self._generate_deterministic_vector(text, tenant_id, model_version)
            result = EmbeddingResult(
                vector=vector,
                model_version=model_version,
                generated_at=datetime.utcnow(),
                token_count=len(text.split())  # Rough token count approximation
            )
            results.append(result)
        
        return results
    
    def _generate_deterministic_vector(
        self,
        text: str,
        tenant_id: str,
        model_version: str,
    ) -> List[float]:
        """
        Generate a deterministic pseudo-random vector based on input hash.
        
        Uses SHA256 hash of (text + tenant_id + model_version) seeded into
        a deterministic random number generator to produce reproducible vectors.
        
        Args:
            text: Input text
            tenant_id: Tenant identifier
            model_version: Model version string
        
        Returns:
            List of floats representing the embedding vector
        """
        # Create deterministic seed from inputs
        seed_string = f"{text}:{tenant_id}:{model_version}"
        hash_digest = hashlib.sha256(seed_string.encode()).hexdigest()
        seed = int(hash_digest[:16], 16)
        
        # Use seeded random for deterministic results
        local_random = random.Random(seed)
        
        # Generate vector with values in [-1, 1] range (typical for normalized embeddings)
        vector = [local_random.uniform(-1, 1) for _ in range(self.vector_dimension)]
        
        # Normalize to unit length (common practice for embeddings)
        magnitude = sum(x * x for x in vector) ** 0.5
        if magnitude > 0:
            vector = [x / magnitude for x in vector]
        
        return vector
    
    def get_vector_dimension(self, model_version: str) -> int:
        """Returns the configured vector dimension."""
        return self.vector_dimension
    
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
