"""
Base normalizer strategy interface.

All source-specific normalizers must implement this interface.
No source-specific branching in core services — all branching is encapsulated
in strategy implementations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple
from app.core.models import IdentityHint, PermissionLevel


class NormalizerStrategy(ABC):
    """
    Abstract base class for source-specific normalization strategies.
    
    Each source type (google_drive, google_gmail, etc.) implements this interface
    to provide source-specific extraction logic without polluting core services.
    """
    
    @abstractmethod
    def get_source_type(self) -> str:
        """Return the source type identifier (e.g., 'google_drive')."""
        ...

    @abstractmethod
    async def extract_text(self, raw: Dict[str, Any]) -> str:
        """
        Extract plain text content from raw document.
        
        Must be bounded — see MAX_EXTRACTED_CHARS config.
        May call OCR for images/scanned documents.
        
        Args:
            raw: Raw document object from source
            
        Returns:
            Extracted plain text (bounded)
        """
        ...

    @abstractmethod
    def map_metadata(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and validate structured metadata.
        
        Re-validate against the source's manifest allowlist (Block B).
        Do not trust metadata blindly.
        
        Args:
            raw: Raw document object from source
            
        Returns:
            Validated metadata dict
        """
        ...

    @abstractmethod
    def extract_permission_hints(self, raw: Dict[str, Any]) -> List[Tuple[IdentityHint, PermissionLevel]]:
        """
        Extract raw permission grants as (identity hint, level) pairs.
        
        NOT yet resolved to principal_id — that happens in IdentityResolver.
        
        Args:
            raw: Raw document object from source
            
        Returns:
            List of (IdentityHint, PermissionLevel) tuples
        """
        ...

    @abstractmethod
    def extract_containers(self, raw: Dict[str, Any]) -> List[str]:
        """
        Extract parent container IDs for inheritance.
        
        Args:
            raw: Raw document object from source
            
        Returns:
            List of container IDs (folders, mailboxes, etc.)
        """
        ...

    @abstractmethod
    def extract_identity_hints(self, raw: Dict[str, Any]) -> Dict[str, IdentityHint]:
        """
        Extract identity hints for special roles (owner, creator, modifier).
        
        Keys present depend on source capabilities.
        Common keys: 'owner', 'creator', 'last_modifier'
        
        Args:
            raw: Raw document object from source
            
        Returns:
            Dict mapping role names to IdentityHint objects
        """
        ...
