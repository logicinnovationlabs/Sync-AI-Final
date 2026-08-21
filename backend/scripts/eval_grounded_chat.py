"""Run grounded-chat evaluation cases through the Block L orchestrator pipeline.

Usage (from backend/):
  python scripts/eval_grounded_chat.py
  python scripts/eval_grounded_chat.py --live
  ASSISTANT_DEBUG=1 python scripts/eval_grounded_chat.py

Default provider is FakeChatProvider (offline, CI-safe).
``--live`` uses OpenRouter/Qwen via OPENROUTER_API_KEY + QWEN_MODEL.

Accuracy is defined in tests/fixtures/assistant_eval.json. This script does
not claim 100% accuracy; it reports pass/fail, latency, retrieved chunks,
citations, and unsupported-answer rate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.assistant.core.graph import OrchestratorGraph, default_acl_from_claims
from app.services.assistant.domain.models import OrchestratorRequest, ToolCall, ToolResult
from app.services.assistant.infrastructure.chat_provider import (
    FakeChatProvider,
    OpenRouterChatProvider,
    debug_source_chunks,
    is_refuse_answer,
)

FIXTURE = ROOT / "tests" / "fixtures" / "assistant_eval.json"
TENANT = "tenant-eval"
USER = "user-eval"

_ID_RE = re.compile(r"\b(?:doc|INV|GST|TV)[-_A-Z0-9]{2,}\b", re.IGNORECASE)
_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


class StubToolbox:
    """ACL-already-filtered retrieval stub used by the eval pipeline."""

    signals_url = "http://127.0.0.1:9"

    def __init__(self, hits: List[Dict[str, Any]]) -> None:
        self.hits = hits

    async def execute(
        self,
        call: ToolCall,
        *,
        authorization: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> ToolResult:
        if call.tool_name in ("lexical_search", "vector_search"):
            return ToolResult(
                tool_name=call.tool_name,
                ok=True,
                payload={"results": self.hits},
            )
        if call.tool_name == "signal_lookup":
            return ToolResult(tool_name=call.tool_name, ok=True, payload={})
        if call.tool_name == "read_document":
            doc_id = str(call.query_params.get("document_id") or "")
            hit = next((h for h in self.hits if h.get("document_id") == doc_id), None)
            if hit is None:
                return ToolResult(
                    tool_name=call.tool_name, ok=False, error="not_found", payload={}
                )
            return ToolResult(
                tool_name=call.tool_name,
                ok=True,
                payload={
                    "document_id": hit["document_id"],
                    "title": hit.get("title"),
                    "body": hit.get("body") or hit.get("snippet"),
                },
            )
        return ToolResult(tool_name=call.tool_name, ok=False, error="unknown", payload={})


class InMemoryMemory:
    """Session store that does not require Postgres (eval / unit use)."""

    def __init__(self) -> None:
        self._sessions: Dict[tuple[str, str], Any] = {}

    def ensure_schema(self) -> None:
        return

    def load_session(self, tenant_id: str, session_id: str):
        return self._sessions.get((tenant_id, session_id))

    def save_session(self, ctx) -> None:
        self._sessions[(ctx.tenant_id, ctx.session_id)] = ctx


def _context_blob(hits: Sequence[Dict[str, Any]]) -> str:
    parts = []
    for hit in hits:
        parts.append(str(hit.get("document_id") or ""))
        parts.append(str(hit.get("title") or ""))
        parts.append(str(hit.get("snippet") or ""))
        parts.append(str(hit.get("body") or ""))
    return " ".join(parts).lower()


def unsupported_markers(answer: str, hits: Sequence[Dict[str, Any]]) -> List[str]:
    if is_refuse_answer(answer):
        return []
    ctx = _context_blob(hits)
    found: List[str] = []
    for token in _ID_RE.findall(answer or ""):
        if token.lower() not in ctx:
            found.append(token)
    for token in _NUM_RE.findall(answer or ""):
        if token not in ctx and token not in (answer and []):
            # citation indexes like [1] are stripped by word-boundary \d
            if token.lower() not in ctx:
                found.append(token)
    # Drop tiny citation-like numbers 1-8 if they appear as source indexes.
    cleaned = []
    for token in found:
        if token.isdigit() and 1 <= int(token) <= 8:
            continue
        cleaned.append(token)
    return cleaned


def evaluate_case(case: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    hits = list(result.get("ranked_hits") or [])
    retrieved_ids = [str(h.get("document_id") or "") for h in hits if h.get("document_id")]
    expected_ids = list(case.get("expected_source_ids") or [])
    answer = str(result.get("response_text") or "")
    facts = [str(f).lower() for f in (case.get("required_facts") or [])]
    expect_refuse = bool(case.get("expect_refuse"))
    missing_sources = [sid for sid in expected_ids if sid not in retrieved_ids]
    missing_facts = [f for f in facts if f not in answer.lower()]
    refused = is_refuse_answer(answer)
    unsupported = unsupported_markers(answer, hits)
    if expect_refuse:
        passed = refused and not missing_sources
        fail_reason = None if passed else "expected refuse from missing context"
    else:
        passed = not missing_sources and not missing_facts and not refused
        fail_reason = None
        if missing_sources:
            fail_reason = f"missing sources {missing_sources}"
        elif refused:
            fail_reason = "unexpected refuse"
        elif missing_facts:
            fail_reason = f"missing facts {missing_facts}"
    if unsupported and not expect_refuse:
        passed = False
        fail_reason = f"unsupported markers {unsupported}"
    return {
        "id": case.get("id"),
        "question": case.get("question"),
        "passed": passed,
        "fail_reason": fail_reason,
        "answer": answer,
        "latency_ms": result.get("latency_ms"),
        "timings_ms": result.get("timings_ms") or {},
        "retrieved_ids": retrieved_ids,
        "retrieved_chunks": debug_source_chunks(hits),
        "citations": result.get("citations") or [],
        "refused": refused,
        "unsupported_markers": unsupported,
        "chat_provider_name": result.get("chat_provider_name"),
        "generation_error": result.get("generation_error") or "",
    }


async def run_case(
    case: Dict[str, Any],
    corpus: List[Dict[str, Any]],
    provider,
) -> Dict[str, Any]:
    hits = [] if case.get("empty_corpus") else list(corpus)
    graph = OrchestratorGraph(
        StubToolbox(hits),
        InMemoryMemory(),  # type: ignore[arg-type]
        chat_provider=provider,
        max_tool_call_rounds=2,
    )
    req = OrchestratorRequest(
        tenant_id=TENANT,
        user_id=USER,
        session_id=f"eval-{case.get('id')}-{uuid4().hex[:8]}",
        prompt=str(case.get("question") or ""),
    )
    started = time.perf_counter()
    result = await graph.arun(
        req,
        acl_compiled_filter=default_acl_from_claims([f"user:{USER}"]),
    )
    result["latency_ms"] = result.get("latency_ms") or (time.perf_counter() - started) * 1000.0
    return evaluate_case(case, result)


def load_fixture(path: Path = FIXTURE) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


async def run_eval(*, live: bool, include_live_only: bool) -> Dict[str, Any]:
    data = load_fixture()
    corpus = list(data.get("corpus") or [])
    cases = list(data.get("cases") or [])
    if live:
        provider = OpenRouterChatProvider.from_settings()
    else:
        provider = FakeChatProvider()
        cases = [c for c in cases if not c.get("live_only")]
    if not include_live_only:
        cases = [c for c in cases if not c.get("live_only")]

    rows = []
    for case in cases:
        rows.append(await run_case(case, corpus, provider))

    n = len(rows) or 1
    unsupported_rate = sum(1 for r in rows if r["unsupported_markers"]) / n
    refuse_rate = sum(1 for r in rows if r["refused"]) / n
    passed = sum(1 for r in rows if r["passed"])
    return {
        "provider": provider.name,
        "accuracy_definition": data.get("accuracy_definition"),
        "passed": passed,
        "total": len(rows),
        "unsupported_answer_rate": unsupported_rate,
        "refuse_rate": refuse_rate,
        "cases": rows,
    }


def _print_report(report: Dict[str, Any]) -> None:
    print(f"provider={report['provider']} passed={report['passed']}/{report['total']}")
    print(
        "unsupported_answer_rate="
        f"{report['unsupported_answer_rate']:.2f} refuse_rate={report['refuse_rate']:.2f}"
    )
    print()
    for row in report["cases"]:
        status = "PASS" if row["passed"] else "FAIL"
        print(f"[{status}] {row['id']}  {row['latency_ms']:.1f}ms  provider={row['chat_provider_name']}")
        print(f"  Q: {row['question']}")
        print(f"  A: {row['answer'][:300]}")
        print(f"  retrieved: {row['retrieved_ids']}")
        cites = [c.get('document_id') for c in row['citations']]
        print(f"  citations: {cites}")
        if row["fail_reason"]:
            print(f"  reason: {row['fail_reason']}")
        print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Grounded chat evaluation")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call OpenRouter/Qwen instead of FakeChatProvider",
    )
    parser.add_argument(
        "--include-live-only",
        action="store_true",
        help="Also run cases marked live_only (implies --live)",
    )
    args = parser.parse_args(argv)
    live = bool(args.live or args.include_live_only)
    report = asyncio.run(run_eval(live=live, include_live_only=bool(args.include_live_only)))
    _print_report(report)
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
