"""
Normalizer registry for strategy lookup.

Same pattern as Block B's connector registry — register source-specific strategies
and fall back to GenericFallbackNormalizer for unregistered types.
"""

import logging
from typing import Dict, Type
from app.normalizer.base import NormalizerStrategy

logger = logging.getLogger(__name__)


class NormalizerRegistry:
    """
    Registry for normalizer strategies.
    
    Provides lookup by source_type with fallback to GenericFallbackNormalizer
    for future sources that don't yet have a real implementation.
    """
    
    def __init__(self):
        self._strategies: Dict[str, Type[NormalizerStrategy]] = {}
        self._fallback: Type[NormalizerStrategy] | None = None
    
    def register(self, source_type: str, strategy_class: Type[NormalizerStrategy]) -> None:
        """
        Register a normalizer strategy for a source type.
        
        Args:
            source_type: Source type identifier
            strategy_class: Strategy class (not instance)
        """
        self._strategies[source_type] = strategy_class
        logger.info(f"Registered normalizer strategy for {source_type}: {strategy_class.__name__}")
    
    def register_fallback(self, strategy_class: Type[NormalizerStrategy]) -> None:
        """
        Register the fallback strategy for unregistered source types.
        
        Args:
            strategy_class: Fallback strategy class
        """
        self._fallback = strategy_class
        logger.info(f"Registered fallback normalizer: {strategy_class.__name__}")
    
    def get(self, source_type: str) -> NormalizerStrategy:
        """
        Get normalizer strategy instance for source type.
        
        Falls back to GenericFallbackNormalizer if not registered.
        
        Args:
            source_type: Source type identifier
            
        Returns:
            NormalizerStrategy instance
        """
        strategy_class = self._strategies.get(source_type)
        
        if not strategy_class:
            if self._fallback:
                logger.warning(
                    f"No normalizer registered for {source_type}, "
                    f"using fallback: {self._fallback.__name__}"
                )
                strategy_class = self._fallback
            else:
                raise ValueError(
                    f"No normalizer registered for source_type '{source_type}' "
                    f"and no fallback configured"
                )
        
        return strategy_class()


# Global registry instance
normalizer_registry = NormalizerRegistry()
