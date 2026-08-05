"""
Generic fallback normalizer for unregistered source types.

Provides degraded-but-functional normalization for future sources that don't
yet have a real implementation. Documents with zero permission hints will route
to the DLQ (Block B's existing empty-permissions rule).
"""

import logging
from typing import Dict, Any, List, Tuple
from app.normalizer.base import NormalizerStrategy
from app.core.models import IdentityHint, PermissionLevel

logger = logging.getLogger(__name__)


class GenericFallbackNormalizer(NormalizerStrategy):
    """
    Generic fallback normalizer for unregistered source types.
    
    Used when a future connector (Outlook, Tally, WhatsApp) is added before
    its real normalizer is implemented. Provides best-effort extraction.
    """
    
    def get_source_type(self) -> str:
        return "generic"
    
    async def extract_text(self, raw: Dict[str, Any]) -> str:
        """
        Best-effort text extraction.
        
        Looks for common field names that might contain content.
        """
        # Try common content field names
        for field in ["content", "text", "body", "description", "snippet", "title", "name"]:
            value = raw.get(field)
            if value and isinstance(value, str):
                logger.info(f"GenericFallbackNormalizer: extracted text from '{field}' field")
                return value
        
        logger.warning("GenericFallbackNormalizer: no content field found, returning empty string")
        return ""
    
    def map_metadata(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Best-effort metadata extraction.
        
        Returns empty dict — no metadata validation without a real strategy.
        """
        logger.warning("GenericFallbackNormalizer: no metadata mapping, returning empty dict")
        return {}
    
    def extract_permission_hints(self, raw: Dict[str, Any]) -> List[Tuple[IdentityHint, PermissionLevel]]:
        """
        Best-effort permission extraction.
        
        Returns empty list — documents with zero permission hints will route to DLQ
        per Block B's existing empty-permissions rule (do not silently grant or drop).
        """
        logger.warning(
            "GenericFallbackNormalizer: no permission hints, document will route to DLQ if "
            "Block B's empty-permissions validation is active"
        )
        return []
    
    def extract_containers(self, raw: Dict[str, Any]) -> List[str]:
        """
        Best-effort container extraction.
        
        Returns empty list — no inheritance without a real strategy.
        """
        return []
    
    def extract_identity_hints(self, raw: Dict[str, Any]) -> Dict[str, IdentityHint]:
        """
        Best-effort identity extraction.
        
        Returns empty dict — no role identities without a real strategy.
        """
        return {}
