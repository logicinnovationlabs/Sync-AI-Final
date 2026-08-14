"""LangGraph state machine for Block L orchestration."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.services.assistant.core.intent_router import Intent, classify_intent
from app.services.assistant.core.ranker_boost import (
    RankedHit,
    apply_signal_boost,
    extract_base_hits,
    max_confidence,
)
from app.services.assistant.domain.models import (
    OrchestratorRequest,
    SessionContext,
    ToolCall,
    ToolResult,
)
from app.services.assistant.infrastructure.memory_store import EpisodicMemoryStore
from app.services.assistant.infrastructure.tools import SearchToolbox, encode_acl_terms

logger = logging.getLogger(__name__)

# Search vs Read switch threshold (spec §2).
CONFIDENCE_THRESHOLD = 0.6


class OrchestratorState(TypedDict, total=False):
    request: Dict[str, Any]
    authorization: Optional[str]
    acl_compiled_filter: bytes
    intent: str
    session: Dict[str, Any]
    tool_results: List[Dict[str, Any]]
    ranked_hits: List[Dict[str, Any]]
    base_hits: List[Dict[str, Any]]
    signals: Dict[str, Any]
    response_text: str
    citations: List[Dict[str, Any]]
    used_document_reader: bool
    latency_ms: float
    errors: List[str]


class OrchestratorGraph:
    """intent_router -> parallel_searcher -> personalized_ranker -> response_generator -> END"""

    def __init__(
        self,
        toolbox: SearchToolbox,
        memory: EpisodicMemoryStore,
        *,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ) -> None:
        self.toolbox = toolbox
        self.memory = memory
        self.confidence_threshold = confidence_threshold
        self._graph = build_orchestrator_graph(self)

    async def arun(
        self,
        request: OrchestratorRequest,
        *,
        acl_compiled_filter: bytes,
        authorization: Optional[str] = None,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        ctx = self.memory.load_session(request.tenant_id, request.session_id)
        if ctx is None:
            ctx = SessionContext(
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                session_id=request.session_id,
            )
        elif ctx.tenant_id != request.tenant_id:
            raise PermissionError("cross-tenant session access denied")
        ctx.append_user(request.prompt)

        initial: OrchestratorState = {
            "request": request.model_dump(),
            "authorization": authorization,
            "acl_compiled_filter": acl_compiled_filter,
            "session": ctx.model_dump(),
            "tool_results": [],
            "ranked_hits": [],
            "base_hits": [],
            "signals": {},
            "response_text": "",
            "citations": [],
            "used_document_reader": False,
            "errors": [],
        }
        final = await self._graph.ainvoke(initial)
        final["latency_ms"] = (time.perf_counter() - started) * 1000.0

        # Persist session (tenant-scoped).
        session_data = final.get("session") or ctx.model_dump()
        saved = SessionContext.model_validate(session_data)
        saved.append_assistant(
            final.get("response_text") or "",
            citations=final.get("citations") or [],
            intent=final.get("intent"),
        )
        saved.intent_stack = list(saved.intent_stack) + [str(final.get("intent") or "")]
        saved.last_document_ids = [
            h.get("document_id") for h in (final.get("ranked_hits") or []) if h.get("document_id")
        ][:10]
        self.memory.save_session(saved)
        final["session"] = saved.model_dump()

        # Fire-and-forget activity ingest on a daemon thread — must not block
        # the response stream or pin an AsyncClient to this event loop.
        import threading

        threading.Thread(
            target=self._emit_activity_sync,
            args=(request, final, authorization, acl_compiled_filter),
            daemon=True,
        ).start()
        return final

    def _emit_activity_sync(
        self,
        request: OrchestratorRequest,
        final: Dict[str, Any],
        authorization: Optional[str],
        acl: bytes,
    ) -> None:
        try:
            import httpx

            top = (final.get("ranked_hits") or [{}])[0]
            event = {
                "event_id": str(uuid.uuid4()),
                "actor_principal_id": request.user_id,
                "object_id": top.get("document_id") or "orchestrator:none",
                "event_type": "referenced",
                "source_system": "assistant_orchestrator",
                "event_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "session_id": request.session_id,
                "context_json": {
                    "prompt_len": len(request.prompt),
                    "latency_ms": final.get("latency_ms"),
                    "intent": final.get("intent"),
                },
                "privacy_level": "restricted",
            }
            headers = {
                "X-ACL-Compiled-Filter": acl.hex(),
                "Content-Type": "application/json",
            }
            if authorization:
                headers["Authorization"] = authorization
            with httpx.Client(timeout=5.0) as client:
                client.post(
                    f"{self.toolbox.signals_url}/activity/ingest",
                    headers=headers,
                    json={"events": [event]},
                )
        except Exception:  # noqa: BLE001
            logger.exception("activity ingest failed (non-blocking)")

    # ---- graph nodes ----

    async def intent_router(self, state: OrchestratorState) -> OrchestratorState:
        req = state["request"]
        attachments = [a.get("blob_id") for a in (req.get("attachments") or [])]
        intent = classify_intent(req.get("prompt") or "", attachment_ids=attachments)
        return {**state, "intent": intent.value}

    async def parallel_searcher(self, state: OrchestratorState) -> OrchestratorState:
        req = state["request"]
        intent = state.get("intent") or Intent.SEARCH.value
        acl = state["acl_compiled_filter"]
        auth = state.get("authorization")
        tenant_id = req["tenant_id"]
        prompt = req.get("prompt") or ""
        errors = list(state.get("errors") or [])
        results: List[ToolResult] = []

        if intent == Intent.CHAT.value:
            return {**state, "tool_results": [], "errors": errors}

        if intent == Intent.READ.value:
            doc_id = None
            atts = req.get("attachments") or []
            if atts:
                doc_id = atts[0].get("blob_id")
            if not doc_id:
                # fall through to search when no explicit blob
                intent = Intent.SEARCH.value
            else:
                call = ToolCall(
                    tool_name="read_document",
                    query_params={"document_id": doc_id},
                    acl_compiled_filter=acl,
                )
                results.append(
                    await self.toolbox.execute(call, authorization=auth, tenant_id=tenant_id)
                )
                return {
                    **state,
                    "intent": Intent.READ.value,
                    "tool_results": [r.model_dump() for r in results],
                    "used_document_reader": True,
                    "errors": errors,
                }

        # Parallel lexical + vector via Federator fan-out wrappers + signal lookup.
        calls = [
            ToolCall(
                tool_name="lexical_search",
                query_params={"query": prompt, "size": 10},
                acl_compiled_filter=acl,
            ),
            ToolCall(
                tool_name="vector_search",
                query_params={"query": prompt, "size": 10},
                acl_compiled_filter=acl,
            ),
            ToolCall(
                tool_name="signal_lookup",
                query_params={"user_id": req["user_id"]},
                acl_compiled_filter=acl,
            ),
        ]
        gathered = await asyncio.gather(
            *[self.toolbox.execute(c, authorization=auth, tenant_id=tenant_id) for c in calls]
        )
        results.extend(gathered)
        signals: Dict[str, Any] = {}
        for r in gathered:
            if r.tool_name == "signal_lookup" and r.ok:
                signals = r.payload
            if not r.ok and r.error:
                errors.append(f"{r.tool_name}: {r.error}")

        return {
            **state,
            "tool_results": [r.model_dump() for r in results],
            "signals": signals,
            "errors": errors,
        }

    async def personalized_ranker(self, state: OrchestratorState) -> OrchestratorState:
        """Call Ranking Service output (via Federator results) then apply signal boost."""
        if state.get("intent") == Intent.CHAT.value:
            return state
        if state.get("used_document_reader") and state.get("intent") == Intent.READ.value:
            # Reader path: synthesize a single hit from the document payload.
            for tr in state.get("tool_results") or []:
                if tr.get("tool_name") == "read_document" and tr.get("ok"):
                    payload = tr.get("payload") or {}
                    hit = RankedHit(
                        document_id=str(payload.get("document_id") or ""),
                        base_score=1.0,
                        boosted_score=1.0,
                        title=str(payload.get("title") or ""),
                        snippet=str(payload.get("body") or "")[:500],
                        sources=["document_reader"],
                    )
                    return {
                        **state,
                        "base_hits": [hit.__dict__],
                        "ranked_hits": [hit.__dict__],
                    }
            return state

        # Merge federator payloads (lexical + vector wrappers both hit Federator).
        merged_results: List[Dict[str, Any]] = []
        seen = set()
        for tr in state.get("tool_results") or []:
            if tr.get("tool_name") not in ("lexical_search", "vector_search"):
                continue
            payload = tr.get("payload") or {}
            for item in payload.get("results") or []:
                doc_id = item.get("document_id") or item.get("id")
                if not doc_id or doc_id in seen:
                    continue
                seen.add(doc_id)
                merged_results.append(item)

        base_hits = extract_base_hits({"results": merged_results})
        boosted = apply_signal_boost(base_hits, state.get("signals") or {})

        # Search vs Read switch: below threshold → Document Reader on top blob.
        used_reader = False
        errors = list(state.get("errors") or [])
        if max_confidence(boosted) < self.confidence_threshold and boosted:
            top = boosted[0]
            acl = state["acl_compiled_filter"]
            call = ToolCall(
                tool_name="read_document",
                query_params={"document_id": top.document_id},
                acl_compiled_filter=acl,
            )
            reader = await self.toolbox.execute(
                call,
                authorization=state.get("authorization"),
                tenant_id=state["request"]["tenant_id"],
            )
            tool_results = list(state.get("tool_results") or [])
            tool_results.append(reader.model_dump())
            used_reader = True
            if reader.ok:
                body = str((reader.payload or {}).get("body") or "")
                # Promote reader evidence into the top hit snippet without changing base_score.
                promoted = RankedHit(
                    document_id=top.document_id,
                    base_score=top.base_score,
                    boosted_score=max(top.boosted_score, self.confidence_threshold),
                    title=top.title or str((reader.payload or {}).get("title") or ""),
                    snippet=body[:800] or top.snippet,
                    sources=list(top.sources) + ["document_reader_fallback"],
                    boost_reason="search_vs_read_fallback",
                    meta=dict(top.meta),
                )
                boosted = [promoted] + [h for h in boosted if h.document_id != top.document_id]
            elif reader.error:
                errors.append(f"read_document: {reader.error}")
            return {
                **state,
                "base_hits": [h.__dict__ for h in base_hits],
                "ranked_hits": [h.__dict__ for h in boosted],
                "tool_results": tool_results,
                "used_document_reader": used_reader,
                "errors": errors,
            }

        return {
            **state,
            "base_hits": [h.__dict__ for h in base_hits],
            "ranked_hits": [h.__dict__ for h in boosted],
            "used_document_reader": used_reader,
            "errors": errors,
        }

    async def response_generator(self, state: OrchestratorState) -> OrchestratorState:
        intent = state.get("intent")
        hits = state.get("ranked_hits") or []
        if intent == Intent.CHAT.value:
            text = (
                "I can search your tenant corpus, open a specific document, "
                "or answer with citations from retrieved sources. "
                "Ask me to find something or open a document."
            )
            return {**state, "response_text": text, "citations": []}

        if not hits:
            text = "I could not find accessible documents for that request."
            return {**state, "response_text": text, "citations": []}

        lines = []
        citations = []
        for i, h in enumerate(hits[:5], start=1):
            snippet = (h.get("snippet") or "").strip().replace("\n", " ")
            title = h.get("title") or h.get("document_id")
            lines.append(f"{i}. {title}: {snippet[:240]}")
            citations.append(
                {
                    "document_id": h.get("document_id"),
                    "quote": snippet[:200],
                    "score": h.get("boosted_score"),
                    "base_score": h.get("base_score"),
                }
            )
        prefix = "Here is what I found"
        if state.get("used_document_reader"):
            prefix += " (including a deep document read)"
        text = prefix + ":\n" + "\n".join(lines)
        return {**state, "response_text": text, "citations": citations}


def build_orchestrator_graph(owner: OrchestratorGraph):
    graph = StateGraph(OrchestratorState)
    graph.add_node("intent_router", owner.intent_router)
    graph.add_node("parallel_searcher", owner.parallel_searcher)
    graph.add_node("personalized_ranker", owner.personalized_ranker)
    graph.add_node("response_generator", owner.response_generator)
    graph.add_edge(START, "intent_router")
    graph.add_edge("intent_router", "parallel_searcher")
    graph.add_edge("parallel_searcher", "personalized_ranker")
    graph.add_edge("personalized_ranker", "response_generator")
    graph.add_edge("response_generator", END)
    return graph.compile()


def default_acl_from_claims(acl_terms: List[str] | None) -> bytes:
    return encode_acl_terms(list(acl_terms or []))
