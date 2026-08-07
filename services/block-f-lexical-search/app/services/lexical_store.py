"""Abstract lexical store interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LexicalStore(ABC):
    """Tenant-scoped lexical index with mandatory ACL prefilter."""

    @abstractmethod
    async def ensure_tenant(self, tenant_id: str) -> None:
        ...

    @abstractmethod
    async def clear_tenant(self, tenant_id: str) -> None:
        ...

    @abstractmethod
    async def index_document(
        self,
        tenant_id: str,
        document_id: str,
        fields: Dict[str, Any],
        *,
        deleted: bool = False,
    ) -> None:
        ...

    @abstractmethod
    async def delete_document(self, tenant_id: str, document_id: str) -> None:
        ...

    @abstractmethod
    async def search(
        self,
        tenant_id: str,
        query: str,
        acl_terms: List[str],
        *,
        filters: Optional[Dict[str, Any]] = None,
        facets: Optional[List[str]] = None,
        from_: int = 0,
        size: int = 20,
    ) -> Dict[str, Any]:
        """
        Return {"results": [...], "facets": {...}, "total": int}.

        ACL filter MUST be applied in filter context before scoring.
        """
        ...

    @abstractmethod
    async def get_document(
        self, tenant_id: str, document_id: str
    ) -> Optional[Dict[str, Any]]:
        ...
