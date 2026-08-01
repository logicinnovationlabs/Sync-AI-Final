"""
BaseConnector abstract class - the contract all future connectors must implement.

This is the ONLY contract that sync.py, indexer.py, and query.py ever see.
Adding connector #11 must require zero edits to any core file.

Critical for Signoff A1-A7.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol
from pydantic import BaseModel, Field, field_validator


class TokenStore(Protocol):
    """Protocol for storing and retrieving OAuth tokens securely."""
    
    def get_token(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a token by key."""
        ...

    def set_token(self, key: str, token_data: Dict[str, Any]) -> None:
        """Store a token by key."""
        ...


@dataclass
class DeltaResult:
    """Result of a delta sync (incremental crawl)."""

    documents: List[Dict[str, Any]]
    next_cursor: Optional[str]
    has_more: bool


@dataclass
class DeletionResult:
    """Result of a deletion sync."""

    deleted_ids: List[str]
    next_cursor: Optional[str]
    has_more: bool


class UnifiedDocument(BaseModel):
    """
    Canonical document format that all connectors must transform their raw data into.
    This is what the blind orchestrator passes to the indexer.
    """

    id: str = Field(..., description="Globally unique document ID")
    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Full text content")
    source_type: str = Field(..., description="Source connector type (e.g., 'google_drive')")
    url: str = Field(..., description="Deep link back to the source")
    permissions: List[str] = Field(
        ..., description="ACL list, each prefixed 'user:' or 'group:'"
    )
    created_at: datetime = Field(..., description="Document creation timestamp")
    updated_at: datetime = Field(..., description="Document last modified timestamp")
    source_updated_at: datetime = Field(
        ..., description="Vendor's own last-modified timestamp (required for delta cursors)"
    )
    structured_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Source-specific metadata"
    )

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, v: List[str]) -> List[str]:
        """Ensure all permissions are properly prefixed."""
        for p in v:
            if not p.startswith(("user:", "group:")):
                raise ValueError(f"Permission '{p}' must be prefixed 'user:' or 'group:'")
        return v


class BaseConnector(ABC):
    """
    Abstract base class for all source connectors.
    
    Every connector implements this contract; the orchestrator never imports
    specific connectors by name.
    """

    def __init__(self, config: Dict[str, Any], token_store: TokenStore):
        """
        Initialize the connector.
        
        Args:
            config: Connector-specific configuration (credentials, instance URL, etc.)
            token_store: Secure token storage for OAuth refresh tokens
        """
        self.config = config
        self.token_store = token_store
        self.source_type = self.get_source_type()

    @abstractmethod
    def get_source_type(self) -> str:
        """
        Return the unique source type identifier (e.g., 'google_drive', 'slack').
        
        This is used for routing and indexing.
        """
        ...

    @abstractmethod
    async def get_valid_token(self) -> str:
        """
        Return a valid access token, refreshing if necessary.
        
        This method handles OAuth refresh logic internally.
        
        Returns:
            A valid bearer token string.
            
        Raises:
            Exception if token refresh fails.
        """
        ...

    @abstractmethod
    async def fetch_delta(self, since: datetime, cursor: Optional[str]) -> DeltaResult:
        """
        Fetch documents changed since a given timestamp.
        
        Args:
            since: Only return documents modified after this timestamp
            cursor: Pagination cursor from a previous call (None for first page)
            
        Returns:
            DeltaResult with documents, next_cursor, and has_more flag.
        """
        ...

    @abstractmethod
    async def fetch_deleted_ids(
        self, since: datetime, cursor: Optional[str]
    ) -> DeletionResult:
        """
        Fetch IDs of documents deleted since a given timestamp.
        
        Args:
            since: Only return deletions after this timestamp
            cursor: Pagination cursor from a previous call (None for first page)
            
        Returns:
            DeletionResult with deleted_ids, next_cursor, and has_more flag.
            
        Raises:
            NotImplementedError if the source doesn't support deletion tracking.
        """
        ...

    @abstractmethod
    async def transform(self, raw_documents: List[Dict[str, Any]]) -> List[UnifiedDocument]:
        """
        Transform raw source documents into UnifiedDocument format.
        
        Args:
            raw_documents: Documents in the source's native format
            
        Returns:
            List of UnifiedDocument instances ready for indexing.
        """
        ...
