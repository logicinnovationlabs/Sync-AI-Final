"""Index document models for POST /_internal/index."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, AliasChoices


class IndexDocumentRequest(BaseModel):
    """Upsert a canonical document into the lexical index."""

    document_id: str
    tenant_id: str
    fields: Dict[str, Any] = Field(
        ...,
        description="Indexed fields including acl_filter_terms",
    )
    deleted: bool = False

    model_config = {"populate_by_name": True}


class IndexDocumentResponse(BaseModel):
    indexed: int
    tenant_id: str
    document_ids: List[str]


class CanonicalDocumentFields(BaseModel):
    """Normalized field set for lexical indexing (§17.1)."""

    title: str = ""
    body_text: str = ""
    comments_text: str = ""
    file_path: str = ""
    repository: str = ""
    object_type: str = ""
    source: str = ""
    owner: str = ""
    updated_at: Optional[str] = None
    container_path: str = ""
    language: str = ""
    tags: List[str] = Field(default_factory=list)
    acl_filter_terms: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("acl_filter_terms", "acl_terms"),
    )
    hidden_fields: List[str] = Field(
        default_factory=list,
        description="Field names redacted from snippets for this ACL context",
    )

    model_config = {"populate_by_name": True}
