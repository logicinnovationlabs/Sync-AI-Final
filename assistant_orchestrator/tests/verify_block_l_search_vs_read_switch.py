#!/usr/bin/env python
"""Prove 0.6 confidence threshold routes to Document Reader fallback."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time as time_mod

import uvicorn

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from assistant_orchestrator.core.graph import CONFIDENCE_THRESHOLD, OrchestratorGraph
from assistant_orchestrator.domain.models import OrchestratorRequest
from assistant_orchestrator.infrastructure.memory_store import EpisodicMemoryStore
from assistant_orchestrator.infrastructure.tools import SearchToolbox, encode_acl_terms
from assistant_orchestrator.tests._stub_backends import create_stub_app, captured

PORT = int(os.getenv("BLOCK_L_STUB_PORT", "18993"))
BASE = f"http://127.0.0.1:{PORT}"


def _start_server():
    app = create_stub_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time_mod.time() + 10
    import urllib.request
    while time_mod.time() < deadline:
        try:
            urllib.request.urlopen(f"{BASE}/health", timeout=1)
            return server
        except Exception:
            time_mod.sleep(0.1)
    raise RuntimeError("stub server failed to start")


async def run_case(prompt: str, session_id: str) -> dict:
    mem = EpisodicMemoryStore()
    mem.ensure_schema()
    toolbox = SearchToolbox(
        federator_url=BASE,
        graph_url=BASE,
        document_reader_url=BASE,
        signals_url=BASE,
    )
    graph = OrchestratorGraph(toolbox, mem, confidence_threshold=CONFIDENCE_THRESHOLD)
    req = OrchestratorRequest(
        tenant_id="tenant-switch",
        user_id="user-switch",
        session_id=session_id,
        prompt=prompt,
    )
    acl = encode_acl_terms(["user:user-switch"])
    result = await graph.arun(req, acl_compiled_filter=acl, authorization="Bearer t")
    await toolbox.aclose()
    return result


async def run() -> int:
    captured.clear()
    _start_server()
    print("THRESHOLD", CONFIDENCE_THRESHOLD)

    low = await run_case("find lowconf material", "sess-low")
    high = await run_case("find highconf material", "sess-high")

    def summarize(label, result):
        hits = result.get("ranked_hits") or []
        top = hits[0] if hits else {}
        tools = [t.get("tool_name") for t in (result.get("tool_results") or [])]
        print(label, json.dumps({
            "intent": result.get("intent"),
            "used_document_reader": result.get("used_document_reader"),
            "top_score": top.get("boosted_score"),
            "top_base": top.get("base_score"),
            "top_sources": top.get("sources"),
            "tools": tools,
            "snippet_prefix": (top.get("snippet") or "")[:40],
        }, indent=2))
        return top, tools

    low_top, low_tools = summarize("LOW", low)
    high_top, high_tools = summarize("HIGH", high)

    fails = []
    # Below threshold must trigger reader.
    if not low.get("used_document_reader"):
        fails.append("low-confidence case did not use document reader")
    if "read_document" not in low_tools:
        fails.append("low-confidence missing read_document tool call")
    if low_top.get("base_score", 1) >= CONFIDENCE_THRESHOLD:
        fails.append(f"low case base_score not below threshold: {low_top.get('base_score')}")
    if "DEEP_EXTRACTED_BODY" not in (low_top.get("snippet") or ""):
        fails.append("low case snippet missing deep reader body")

    # Above threshold must NOT fall back to reader.
    if high.get("used_document_reader"):
        fails.append("high-confidence case incorrectly used document reader")
    if "read_document" in high_tools:
        fails.append("high-confidence unexpectedly called read_document")
    if (high_top.get("boosted_score") or 0) < CONFIDENCE_THRESHOLD:
        fails.append(f"high case score below threshold: {high_top.get('boosted_score')}")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
