"""
Normalizer strategies for different source types.

Auto-registers all strategies with the global registry on import.
"""

from app.normalizer.registry import normalizer_registry
from app.normalizer.strategies.google_drive import GoogleDriveNormalizer
from app.normalizer.strategies.google_gmail import GoogleGmailNormalizer
from app.normalizer.strategies.onedrive import OneDriveNormalizer, OutlookNormalizer
from app.normalizer.strategies.generic import GenericFallbackNormalizer

# Register strategies
normalizer_registry.register("google_drive", GoogleDriveNormalizer)
normalizer_registry.register("google_gmail", GoogleGmailNormalizer)
normalizer_registry.register("onedrive", OneDriveNormalizer)
normalizer_registry.register("outlook", OutlookNormalizer)
normalizer_registry.register_fallback(GenericFallbackNormalizer)

__all__ = [
    "GoogleDriveNormalizer",
    "GoogleGmailNormalizer",
    "OneDriveNormalizer",
    "OutlookNormalizer",
    "GenericFallbackNormalizer",
]
