"""FastAPI routes for Block L — POST /orchestrator/chat (streaming) + session mgmt.

Auth is Block A only: ``app.api.deps.get_current_user`` (RS256 + revocation).
No unsigned-JWT fallback and no test-user invention.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.acl.filter import acl_terms_from_jwt, is_fail_closed
from app.services.assistant.core.graph import OrchestratorGraph, default_acl_from_claims
from app.services.assistant.domain.models import BlobRef, OrchestratorRequest
from app.services.assistant.infrastructure.memory_store import EpisodicMemoryStore
from app.services.assistant.infrastructure.tools import SearchToolbox

logger = logging.getLogger(__name__)

router = APIRouter(tags=["orchestrator"])

_memory: Optional[EpisodicMemoryStore] = None
_toolbox: Optional[SearchToolbox] = None
_graph: Optional[OrchestratorGraph] = None


def get_memory() -> EpisodicMemoryStore:
    global _memory
    if _memory is None:
        _memory = EpisodicMemoryStore()
        _memory.ensure_schema()
    return _memory


def get_toolbox() -> SearchToolbox:
    global _toolbox
    if _toolbox is None:
        _toolbox = SearchToolbox()
    return _toolbox


def get_graph() -> OrchestratorGraph:
    global _graph
    if _graph is None:
        _graph = OrchestratorGraph(get_toolbox(), get_memory())
    return _graph


class ChatBody(BaseModel):
    prompt: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    attachments: List[BlobRef] = Field(default_factory=list)


class SessionOut(BaseModel):
    tenant_id: str
    user_id: str
    session_id: str
    turn_count: int
    intent_stack: List[str]


@router.post("/orchestrator/chat")
async def orchestrator_chat(
    body: ChatBody,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    graph: OrchestratorGraph = Depends(get_graph),
):
    """Streaming chat — session-aware orchestration."""
    tenant_id = str(current_user.get("tenant_id") or "")
    user_id = str(
        current_user.get("principal_id")
        or current_user.get("user_id")
        or current_user.get("sub")
        or ""
    )
    if body.tenant_id and body.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="tenant_id mismatch")
    if not tenant_id or not user_id:
        raise HTTPException(status_code=401, detail="tenant_id / principal_id missing")

    acl_terms = acl_terms_from_jwt(current_user)
    if is_fail_closed(acl_terms):
        acl_terms = [f"user:{user_id}"]
    acl_bytes = default_acl_from_claims(acl_terms)

    orch_request = OrchestratorRequest(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=body.session_id,
        prompt=body.prompt,
        attachments=body.attachments,
    )
    authorization = request.headers.get("Authorization")

    result = await graph.arun(
        orch_request, acl_compiled_filter=acl_bytes, authorization=authorization
    )

    async def event_stream() -> AsyncIterator[bytes]:
        # NDJSON stream: meta, then token chunks, then final.
        meta = {
            "type": "meta",
            "intent": result.get("intent"),
            "used_document_reader": result.get("used_document_reader"),
            "latency_ms": result.get("latency_ms"),
        }
        yield (json.dumps(meta) + "\n").encode("utf-8")
        text = result.get("response_text") or ""
        # Chunk for streaming UX without blocking on LLM (deterministic synthesizer).
        chunk_size = 48
        for i in range(0, len(text), chunk_size):
            piece = text[i : i + chunk_size]
            yield (json.dumps({"type": "token", "text": piece}) + "\n").encode("utf-8")
        final = {
            "type": "final",
            "response_text": text,
            "citations": result.get("citations") or [],
            "ranked_hits": result.get("ranked_hits") or [],
            "base_hits": result.get("base_hits") or [],
            "session_id": body.session_id,
            "tenant_id": tenant_id,
            "errors": result.get("errors") or [],
            "llm_prompt": result.get("llm_prompt") or "",
            "tool_call_rounds": result.get("tool_call_rounds") or 0,
            "chat_provider_name": result.get("chat_provider_name") or "",
        }
        yield (json.dumps(final) + "\n").encode("utf-8")

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.get("/orchestrator/sessions/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    memory: EpisodicMemoryStore = Depends(get_memory),
):
    tenant_id = str(current_user.get("tenant_id") or "")
    ctx = memory.load_session(tenant_id, session_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="session not found")
    if ctx.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="cross-tenant session access denied")
    return SessionOut(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        turn_count=len(ctx.history),
        intent_stack=list(ctx.intent_stack),
    )


@router.delete("/orchestrator/sessions/{session_id}")
async def clear_session_hint(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Session clear is a no-op placeholder — isolation enforced on load/save."""
    _ = session_id, current_user
    return {"ok": True}


@router.get("/health")
async def health():
    return {"status": "ok", "service": "assistant_orchestrator"}


def create_app() -> FastAPI:
    app = FastAPI(title="Block L: Assistant Orchestrator", version="0.1.0")
    app.include_router(router)

    @app.on_event("startup")
    def _startup() -> None:
        get_memory().ensure_schema()

    return app
