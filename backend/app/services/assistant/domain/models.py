"""Domain models for Block L Assistant Orchestrator."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class BlobRef(BaseModel):
    """Reference to an attached blob (object-store key or document id)."""

    blob_id: str
    tenant_id: str
    content_type: Optional[str] = None
    filename: Optional[str] = None


class OrchestratorRequest(BaseModel):
    """Inbound chat / orchestration request."""

    tenant_id: str
    user_id: str
    session_id: str
    prompt: str
    attachments: List[BlobRef] = Field(default_factory=list)
    account_email: Optional[str] = None


class ToolName(str, Enum):
    LEXICAL_SEARCH = "lexical_search"
    VECTOR_SEARCH = "vector_search"
    KG_QUERY = "kg_query"
    READ_DOCUMENT = "read_document"
    SIGNAL_LOOKUP = "signal_lookup"


class ToolCall(BaseModel):
    """
    Tool invocation carrying an opaque ACL filter.

    acl_compiled_filter is opaque bytes. Block L must never decode, inspect,
    or branch on its contents — only forward it unmodified to downstream tools.
    (Repo reality: Identity/JWT surface emits List[str] acl_terms; callers wrap
    those terms as UTF-8 JSON bytes without Block L inspecting the payload.)
    """

    tool_name: Literal[
        "lexical_search",
        "vector_search",
        "kg_query",
        "read_document",
        "signal_lookup",
    ]
    query_params: Dict[str, Any] = Field(default_factory=dict)
    acl_compiled_filter: bytes


class ToolResult(BaseModel):
    """Normalized tool response."""

    tool_name: str
    ok: bool
    payload: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    # Echo of the exact ACL bytes that were placed on the outbound request.
    acl_bytes_sent: Optional[bytes] = None
    latency_ms: float = 0.0


class TurnRecord(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class SessionContext(BaseModel):
    """Multi-turn session state, always tenant-scoped."""

    tenant_id: str
    user_id: str
    session_id: str
    history: List[TurnRecord] = Field(default_factory=list)
    intent_stack: List[str] = Field(default_factory=list)
    last_document_ids: List[str] = Field(default_factory=list)

    def append_user(self, prompt: str) -> None:
        self.history.append(TurnRecord(role="user", content=prompt))

    def append_assistant(self, content: str, **meta: Any) -> None:
        self.history.append(TurnRecord(role="assistant", content=content, meta=meta))
