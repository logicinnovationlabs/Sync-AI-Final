"""
Core data models for Block C: Normalization, Identity Resolution, and ACL.

Models:
- PermissionLevel: Enum for permission levels
- CanonicalDocument: Enriched document after normalization
- Principal: Resolved identity (person)
- Group: Group identity with members
- ACLEntry: Materialized permission entry for a document
- ContainerACLEntry: Direct permissions on a container (folder/mailbox)
- ContainerEdge: Parent-child relationship between containers
- IdentityHint: Raw identity information from source
- ResolvedIdentity: Result of identity resolution
"""

from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class PermissionLevel(str, Enum):
    """Permission levels for ACL entries."""
    NONE = "NONE"
    READ = "READ"
    WRITE = "WRITE"
    DELETE = "DELETE"
    OWNER = "OWNER"


class CanonicalDocument(BaseModel):
    """
    Canonical document representation after normalization.
    
    This is the enriched, queryable record that persists in Postgres.
    ID format: f"{source_type}_{source_id}" for stable cross-processing identity.
    """
    id: str                              # f"{source_type}_{source_id}", stable across re-processing
    source_type: str
    source_id: str
    # Any UUID version — seeded tenants often use uuid5, not uuid4.
    tenant_id: UUID

    title: str
    content: str                          # extracted plain text, bounded length (MAX_EXTRACTED_CHARS)
    url: Optional[str] = None
    mime_type: str                        # source-stated MIME type
    detected_mime_type: str               # from magic-byte detection — may differ from mime_type
    mime_mismatch: bool = False           # True if source-stated and detected MIME disagree
    file_extension: Optional[str] = None
    size_bytes: Optional[int] = None

    created_at: datetime
    updated_at: datetime
    source_updated_at: datetime

    owner_principal_id: Optional[UUID] = None
    creator_principal_id: Optional[UUID] = None
    last_modifier_principal_id: Optional[UUID] = None

    structured_metadata: Dict[str, Any] = Field(default_factory=dict)   # allowlisted upstream in Block B
    parent_ids: List[str] = Field(default_factory=list)                 # container IDs for inheritance


class Principal(BaseModel):
    """
    Resolved individual identity.
    
    Identity resolution is tenant-scoped — never global.
    Same email seen across Drive + Gmail + Outlook resolves to the same principal_id
    within a tenant, but never merges across tenants.
    """
    id: UUID
    tenant_id: UUID
    email: str                            # normalized (lowercase, stripped)
    name: Optional[str] = None
    source_identities: Dict[str, str] = Field(default_factory=dict)     # {source_type: external_id}
    created_at: datetime
    updated_at: datetime


class Group(BaseModel):
    """
    Group identity with nested membership support.
    
    Groups can contain both individual principals and other groups.
    Cycle-safe expansion is required.
    """
    id: UUID
    tenant_id: UUID
    name: str
    email: Optional[str] = None
    source_type: str
    source_id: str
    member_principal_ids: List[UUID] = Field(default_factory=list)
    member_group_ids: List[UUID] = Field(default_factory=list)          # nested groups — cycle-checked
    created_at: datetime
    updated_at: datetime


class ACLEntry(BaseModel):
    """
    Materialized permission entry for a document.
    
    ACLs are pre-computed and stored, not computed at query time.
    One of principal_id or group_id must be set (mutually exclusive).
    """
    document_id: str
    principal_id: Optional[UUID] = None   # set if grant is to an individual
    group_id: Optional[UUID] = None       # set if grant is to a group (mutually exclusive with principal_id)
    permission: PermissionLevel
    granted_via: str                       # "direct" | "inherited" | "group_membership"
    source_container_id: Optional[str] = None   # which container the inheritance came from
    is_deny: bool = False                  # explicit deny override
    source_type: str
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime


class ContainerACLEntry(BaseModel):
    """
    Direct permissions set on a container (folder, mailbox).
    
    These are stored separately from document ACLs so we can compute inherited
    permissions without having to re-parse documents.
    """
    container_id: str                      # folder/mailbox ID
    principal_id: Optional[UUID] = None
    group_id: Optional[UUID] = None
    permission: PermissionLevel
    is_deny: bool = False
    source_type: str
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime


class ContainerEdge(BaseModel):
    """
    Parent-child relationship between containers.
    
    Used for computing inherited permissions via upward traversal.
    Must be cycle-safe.
    """
    parent_container_id: str
    child_container_id: str
    tenant_id: UUID
    source_type: str
    created_at: datetime


class IdentityHint(BaseModel):
    """
    Raw identity information extracted from source.
    
    This is the input to identity resolution — not yet mapped to a principal_id.
    """
    source_type: str
    external_id: str
    email: Optional[str] = None
    username: Optional[str] = None
    name: Optional[str] = None


class ResolvedIdentity(BaseModel):
    """
    Result of identity resolution.

    Contains the resolved principal and metadata about the match.
    ``matched_on="pending"`` / ``is_pending=True`` means the email was queued
    rather than bound to a principal (Drive-share path only).
    """
    principal_id: Optional[UUID] = None
    principal: Optional[Principal] = None
    confidence: float = 0.0               # 0.0-1.0
    matched_on: str                       # "email" | "username" | "new" | "pending"
    is_pending: bool = False
