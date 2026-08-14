#!/usr/bin/env python
"""Prove Activity Signal boost changes order without mutating base Ranking scores."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time

import uvicorn

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from assistant_orchestrator.core.ranker_boost import apply_signal_boost, extract_base_hits
from assistant_orchestrator.domain.models import ToolCall
from assistant_orchestrator.infrastructure.tools import SearchToolbox, encode_acl_terms
from assistant_orchestrator.tests._stub_backends import create_stub_app, captured

PORT = int(os.getenv("BLOCK_L_STUB_PORT", "18992"))
BASE = f"http://127.0.0.1:{PORT}"


def _start_server():
    app = create_stub_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 10
    import urllib.request
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{BASE}/health", timeout=1)
            return server
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("stub server failed to start")


async def once(user_id: str) -> dict:
    toolbox = SearchToolbox(
        federator_url=BASE,
        graph_url=BASE,
        document_reader_url=BASE,
        signals_url=BASE,
    )
    acl = encode_acl_terms(["user:alice"])
    search = await toolbox.execute(
        ToolCall(tool_name="lexical_search", query_params={"query": "roadmap"}, acl_compiled_filter=acl),
        authorization="Bearer t",
        tenant_id="tenant-a",
    )
    signals = await toolbox.execute(
        ToolCall(tool_name="signal_lookup", query_params={"user_id": user_id}, acl_compiled_filter=acl),
        authorization="Bearer t",
        tenant_id="tenant-a",
    )
    await toolbox.aclose()
    base_hits = extract_base_hits(search.payload)
    boosted = apply_signal_boost(base_hits, signals.payload)
    return {
        "base": [{"id": h.document_id, "base": h.base_score} for h in base_hits],
        "boosted": [
            {"id": h.document_id, "base": h.base_score, "boosted": h.boosted_score, "reason": h.boost_reason}
            for h in boosted
        ],
        "signals_ok": signals.ok,
        "search_ok": search.ok,
    }


async def run() -> int:
    captured.clear()
    _start_server()
    plain = await once("alice")
    boosted = await once("alice-boosted")
    print("PLAIN", json.dumps(plain, indent=2))
    print("BOOSTED", json.dumps(boosted, indent=2))

    fails = []
    if not plain["search_ok"] or not boosted["search_ok"]:
        fails.append("search failed")
    if not plain["signals_ok"] or not boosted["signals_ok"]:
        fails.append("signals failed")

    # Base scores identical across runs (Ranking Service output unmodified).
    plain_base = {x["id"]: x["base"] for x in plain["base"]}
    boost_base = {x["id"]: x["base"] for x in boosted["base"]}
    if plain_base != boost_base:
        fails.append(f"base scores changed: {plain_base} vs {boost_base}")

    # For each hit, boosted.base == original base (additive boost only on boosted_score).
    for h in boosted["boosted"]:
        if abs(h["base"] - boost_base[h["id"]]) > 1e-9:
            fails.append(f"base_score mutated for {h['id']}")

    plain_order = [x["id"] for x in plain["boosted"]]
    boost_order = [x["id"] for x in boosted["boosted"]]
    print("ORDER_PLAIN", plain_order)
    print("ORDER_BOOSTED", boost_order)

    # With signals, doc-beta must rise relative to plain ranking.
    if "doc-beta" not in boost_order:
        fails.append("doc-beta missing")
    else:
        plain_idx = plain_order.index("doc-beta")
        boost_idx = boost_order.index("doc-beta")
        beta_plain = next(x for x in plain["boosted"] if x["id"] == "doc-beta")
        beta_boost = next(x for x in boosted["boosted"] if x["id"] == "doc-beta")
        if beta_boost["boosted"] <= beta_plain["boosted"]:
            fails.append("doc-beta boosted_score did not increase with signals")
        if boost_idx > plain_idx:
            fails.append("doc-beta did not improve rank position with signals")
        print(f"doc-beta rank {plain_idx} -> {boost_idx}; score {beta_plain['boosted']} -> {beta_boost['boosted']}")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
