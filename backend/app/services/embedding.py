"""
Embedding service - generates vector embeddings for documents.

Supports:
- Gemini embeddings (production)
- Fake/deterministic embeddings (tests/dev)

Provider is configured via EMBEDDING_PROVIDER env var.
"""

from typing import List, Protocol
from abc import ABC, abstractmethod
import hashlib

from app.core.config import settings


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""
    
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors (each is a list of floats)
        """
        ...
    
    def get_dimension(self) -> int:
        """Get embedding dimension."""
        ...


class GeminiEmbeddingProvider:
    """
    Gemini-based embedding provider.
    
    Uses Google's Gemini embedding model via the genai SDK.
    """
    
    def __init__(self, api_key: str, model: str = "gemini-embedding-001", dimension: int = 768):
        """
        Initialize Gemini provider.
        
        Args:
            api_key: Gemini API key
            model: Model name
            dimension: Embedding dimension
        """
        self.api_key = api_key
        self.model = model
        self.dimension = dimension
        
        # Import here to avoid requiring google-generativeai in tests
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.genai = genai
    
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using Gemini.
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        for text in texts:
            # Truncate if too long (Gemini has token limits)
            truncated_text = text[:10000]
            
            result = self.genai.embed_content(
                model=self.model,
                content=truncated_text,
            )
            
            embeddings.append(result["embedding"])
        
        return embeddings
    
    def get_dimension(self) -> int:
        """Get embedding dimension."""
        return self.dimension


class FakeEmbeddingProvider:
    """
    Fake/deterministic embedding provider for tests and development.
    
    Generates consistent embeddings based on text hash.
    """
    
    def __init__(self, dimension: int = 768):
        """
        Initialize fake provider.
        
        Args:
            dimension: Embedding dimension
        """
        self.dimension = dimension
    
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate deterministic fake embeddings.
        
        Uses text hash to generate consistent vectors.
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        for text in texts:
            # Generate deterministic vector from text hash
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            
            # Convert hash to floats in [-1, 1] range
            vector = []
            for i in range(self.dimension):
                # Use different parts of the hash
                byte_idx = (i * 2) % len(text_hash)
                hex_val = int(text_hash[byte_idx:byte_idx+2], 16)
                # Normalize to [-1, 1]
                normalized = (hex_val / 128.0) - 1.0
                vector.append(normalized)
            
            embeddings.append(vector)
        
        return embeddings
    
    def get_dimension(self) -> int:
        """Get embedding dimension."""
        return self.dimension


class EmbeddingService:
    """
    Embedding service - facade for different providers.
    
    Selects provider based on configuration.
    """
    
    def __init__(self):
        """Initialize embedding service with configured provider."""
        provider_name = (
            getattr(settings, "embedding_provider", None)
            or getattr(settings, "EMBEDDING_PROVIDER", "fake")
        )
        
        if provider_name == "gemini":
            api_key = (
                getattr(settings, "gemini_api_key", None)
                or getattr(settings, "GEMINI_API_KEY", "")
            )
            model = (
                getattr(settings, "embedding_model", None)
                or getattr(settings, "EMBEDDING_MODEL", "gemini-embedding-001")
            )
            dimension = (
                getattr(settings, "embedding_dimension", None)
                or getattr(settings, "EMBEDDING_DIMENSION", 768)
            )
            
            if not api_key:
                raise ValueError("GEMINI_API_KEY not configured")
            
            self.provider = GeminiEmbeddingProvider(api_key, model, dimension)
        
        elif provider_name == "fake":
            dimension = (
                getattr(settings, "embedding_dimension", None)
                or getattr(settings, "EMBEDDING_DIMENSION", 768)
            )
            self.provider = FakeEmbeddingProvider(dimension)
        
        else:
            raise ValueError(f"Unknown embedding provider: {provider_name}")
    
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for texts.
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        return await self.provider.embed_texts(texts)
    
    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text string
            
        Returns:
            Embedding vector
        """
        embeddings = await self.embed_texts([text])
        return embeddings[0] if embeddings else []
    
    def get_dimension(self) -> int:
        """Get embedding dimension."""
        return self.provider.get_dimension()


# Global embedding service instance
embedding_service = EmbeddingService()
