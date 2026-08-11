"""Pydantic response models for Block K."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StructuredMetadata(BaseModel):
    """Preserved document structure (K3)."""

    headings: List[str] = Field(default_factory=list)
    tables: List[Any] = Field(default_factory=list)
    code_blocks: List[Any] = Field(default_factory=list)
    language: Optional[str] = None


class DocumentResponse(BaseModel):
    """Full-document retrieval response."""

    document_id: str
    tenant_id: str
    title: Optional[str] = None
    body: str
    structured_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    owner_principal_id: Optional[str] = None
