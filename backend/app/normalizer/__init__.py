"""
Normalizer layer for Block C.

This layer extracts text, metadata, and permission hints from raw source documents.
Strategy pattern used to support multiple source types without branching.
"""

from app.normalizer.registry import normalizer_registry
from app.normalizer.base import NormalizerStrategy

__all__ = ["normalizer_registry", "NormalizerStrategy"]
