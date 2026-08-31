"""FastAPI routes for Block L — POST /orchestrator/chat (streaming) + session mgmt.

Auth is Block A only: ``app.api.deps.get_current_user`` (RS256 + revocation).
No unsigned-JWT fallback and no test-user invention.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.api.deps import get_current_user, get_tenant_session
from app.models.user import User
from app.acl.filter import acl_terms_from_jwt, is_fail_closed
from app.services.assistant.core.graph import OrchestratorGraph, default_acl_from_claims
from app.services.assistant.domain.models import BlobRef, OrchestratorRequest
from app.services.assistant.infrastructure.connector_context import build_connector_summary
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
    debug: bool = False


class SessionTurnOut(BaseModel):
    role: str
    content: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)


class SessionOut(BaseModel):
    tenant_id: str
    user_id: str
    session_id: str
    turn_count: int
    intent_stack: List[str]
    title: str = ""
    updated_at: Optional[str] = None
    history: List[SessionTurnOut] = Field(default_factory=list)


class SessionSummaryOut(BaseModel):
    session_id: str
    title: str
    turn_count: int
    updated_at: Optional[str] = None


def _principal_ids(current_user: Dict[str, Any]) -> tuple[str, str]:
    tenant_id = str(current_user.get("tenant_id") or "")
    user_id = str(
        current_user.get("principal_id")
        or current_user.get("user_id")
        or current_user.get("sub")
        or ""
    )
    return tenant_id, user_id


def _title_from_history(history: List[Any]) -> str:
    for turn in history:
        role = getattr(turn, "role", None) or (turn.get("role") if isinstance(turn, dict) else None)
        if role == "user":
            content = getattr(turn, "content", None) or (
                turn.get("content") if isinstance(turn, dict) else ""
            )
            text = str(content or "").strip()
            if text:
                return text[:80]
    return "New chat"


@router.post("/orchestrator/chat")
async def orchestrator_chat(
    body: ChatBody,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    graph: OrchestratorGraph = Depends(get_graph),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """Streaming chat — session-aware orchestration."""
    logger.info(
        "[assistant.pipeline] request received path=/orchestrator/chat session=%s prompt_len=%s",
        body.session_id,
        len(body.prompt or ""),
    )
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

    account_email = str(current_user.get("email") or "").strip() or None
    if not account_email:
        try:
            result = await db_session.execute(
                select(User.email).where(User.principal_id == UUID(user_id))
            )
            account_email = result.scalar_one_or_none()
        except Exception:
            account_email = None

    try:
        connector_summary = await build_connector_summary(tenant_id, user_id)
    except Exception as exc:
        logger.warning("[assistant.chat] build_connector_summary error: %s", exc)
        connector_summary = ""

    orch_request = OrchestratorRequest(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=body.session_id,
        prompt=body.prompt,
        attachments=body.attachments,
        account_email=str(account_email or "") or None,
        connector_summary=connector_summary,
    )
    authorization = request.headers.get("Authorization")

    try:
        result = await graph.arun(
            orch_request, acl_compiled_filter=acl_bytes, authorization=authorization
        )
    except Exception as exc:
        logger.exception("[assistant.pipeline] Error during graph execution: %s", exc)
        result = {
            "response_text": "I encountered an issue processing your request. Please try again in a moment.",
            "generation_error": str(exc),
            "citations": [],
            "ranked_hits": [],
            "base_hits": [],
            "intent": "chat",
            "timings_ms": {},
            "latency_ms": 0.0,
            "chat_provider_name": "fallback",
        }

    async def event_stream() -> AsyncIterator[bytes]:
        # NDJSON stream: meta, then token chunks, then final.
        # Tokens are emitted only after the Qwen (or fake) generation has completed.
        timings = result.get("timings_ms") or {}
        debug_enabled = bool(
            body.debug
            or getattr(settings, "assistant_debug", False)
            or str(getattr(settings, "environment", "")).lower() in ("development", "dev", "local")
        )
        meta = {
            "type": "meta",
            "intent": result.get("intent"),
            "used_document_reader": result.get("used_document_reader"),
            "latency_ms": result.get("latency_ms"),
            "timings_ms": timings,
            "chat_provider_name": result.get("chat_provider_name") or "",
        }
        yield (json.dumps(meta) + "\n").encode("utf-8")
        text = result.get("response_text") or ""
        gen_error = result.get("generation_error") or ""
        # Do not stream a fabricated answer. Provider errors stay in `final`.
        if not gen_error:
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
            "llm_prompt": result.get("llm_prompt") or "" if debug_enabled else "",
            "tool_call_rounds": result.get("tool_call_rounds") or 0,
            "chat_provider_name": result.get("chat_provider_name") or "",
            "timings_ms": timings,
            "generation_error": gen_error,
        }
        if debug_enabled:
            final["debug_retrieval"] = result.get("debug_retrieval") or []
        logger.info(
            "[assistant.pipeline] response rendered session=%s latency_ms=%s provider=%s",
            body.session_id,
            result.get("latency_ms"),
            result.get("chat_provider_name") or "",
        )
        yield (json.dumps(final) + "\n").encode("utf-8")

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.get("/orchestrator/sessions", response_model=List[SessionSummaryOut])
async def list_sessions(
    current_user: Dict[str, Any] = Depends(get_current_user),
    memory: EpisodicMemoryStore = Depends(get_memory),
):
    tenant_id, user_id = _principal_ids(current_user)
    if not tenant_id or not user_id:
        raise HTTPException(status_code=401, detail="tenant_id / principal_id missing")
    try:
        rows = memory.list_sessions_for_user(tenant_id, user_id)
    except Exception as exc:
        logger.warning("[assistant.sessions] Error listing sessions: %s", exc)
        rows = []
    return [SessionSummaryOut.model_validate(row) for row in rows]


@router.get("/orchestrator/sessions/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    memory: EpisodicMemoryStore = Depends(get_memory),
):
    tenant_id, user_id = _principal_ids(current_user)
    try:
        ctx = memory.load_session(tenant_id, session_id)
    except Exception as exc:
        logger.warning("[assistant.get_session] Error loading session %s: %s", session_id, exc)
        ctx = None
    if ctx is None:
        raise HTTPException(status_code=404, detail="session not found")
    if ctx.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="cross-tenant session access denied")
    if ctx.user_id != user_id:
        raise HTTPException(status_code=403, detail="session access denied")
    turns: List[SessionTurnOut] = []
    for turn in ctx.history:
        meta = turn.meta if isinstance(turn.meta, dict) else {}
        citations = meta.get("citations") if isinstance(meta.get("citations"), list) else []
        turns.append(
            SessionTurnOut(
                role=turn.role,
                content=turn.content,
                citations=list(citations),
            )
        )
    return SessionOut(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        turn_count=len(ctx.history),
        intent_stack=list(ctx.intent_stack),
        title=_title_from_history(ctx.history),
        history=turns,
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
