"""
Lexical search store interface and base class.
Abstract interface for OpenSearch and mock implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LexicalStore(ABC):
    """Abstract base class for lexical search stores."""
    
    @abstractmethod
    async def search(
        self,
        tenant_id: str,
        query: str,
        acl_terms: List[str],
        filters: Optional[Dict[str, Any]] = None,
        facets: Optional[List[str]] = None,
        from_: int = 0,
        size: int = 20,
    ) -> Dict[str, Any]:
        """
        Execute lexical search with ACL filtering.
        
        Args:
            tenant_id: Tenant identifier
            query: Search query string
            acl_terms: ACL filter terms (fail-closed if empty)
            filters: Optional metadata filters
            facets: Optional facet fields to aggregate
            from_: Result offset for pagination
            size: Number of results to return
            
        Returns:
            Dict with keys: results (list), facets (dict), total (int)
        """
        pass
    
    @abstractmethod
    async def index_document(
        self,
        tenant_id: str,
        document_id: str,
        document: Dict[str, Any],
    ) -> None:
        """Index a single document."""
        pass
    
    @abstractmethod
    async def index_batch(
        self,
        tenant_id: str,
        documents: List[Dict[str, Any]],
    ) -> int:
        """Bulk index documents. Returns count of indexed docs."""
        pass
    
    @abstractmethod
    async def delete_document(
        self,
        tenant_id: str,
        document_id: str,
    ) -> None:
        """Delete a document from the index."""
        pass
