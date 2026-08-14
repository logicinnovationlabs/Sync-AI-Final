#!/usr/bin/env python
"""Verify ACL compiled filter bytes are forwarded byte-identical to every tool."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from assistant_orchestrator.domain.models import ToolCall
from assistant_orchestrator.infrastructure.tools import SearchToolbox, encode_acl_terms
from assistant_orchestrator.tests._stub_backends import create_stub_app, captured

PORT = int(os.getenv("BLOCK_L_STUB_PORT", "18991"))
BASE = f"http://127.0.0.1:{PORT}"


def _start_server() -> uvicorn.Server:
    app = create_stub_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 10
    import urllib.request
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{BASE}/health", timeout=1)
            return server
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("stub server failed to start")


async def run() -> int:
    captured.clear()
    server = _start_server()
    acl_terms = ["user:alice", "group:eng", "deny:user:eve"]
    acl = encode_acl_terms(acl_terms)
    print("ACL_INPUT_HEX", acl.hex())
    print("ACL_INPUT_JSON", acl.decode("utf-8"))

    sent: List[bytes] = []

    def capture(tool: str, acl_bytes: bytes, meta: Dict[str, Any]) -> None:
        sent.append(acl_bytes)
        print(f"CAPTURE tool={tool} acl_hex={acl_bytes.hex()} url={meta.get('url')}")

    toolbox = SearchToolbox(
        federator_url=BASE,
        graph_url=BASE,
        document_reader_url=BASE,
        signals_url=BASE,
        acl_capture=capture,
    )
    calls = [
        ToolCall(tool_name="lexical_search", query_params={"query": "roadmap"}, acl_compiled_filter=acl),
        ToolCall(tool_name="vector_search", query_params={"query": "roadmap"}, acl_compiled_filter=acl),
        ToolCall(tool_name="kg_query", query_params={"start_node_id": "n1"}, acl_compiled_filter=acl),
        ToolCall(tool_name="read_document", query_params={"document_id": "doc-alpha"}, acl_compiled_filter=acl),
        ToolCall(tool_name="signal_lookup", query_params={"user_id": "alice"}, acl_compiled_filter=acl),
    ]
    results = []
    for c in calls:
        results.append(await toolbox.execute(c, authorization="Bearer test-token", tenant_id="tenant-a"))
    await toolbox.aclose()

    fails = []
    for r in results:
        print(f"RESULT tool={r.tool_name} ok={r.ok} acl_sent_hex={(r.acl_bytes_sent or b'').hex()} err={r.error}")
        if r.acl_bytes_sent != acl:
            fails.append(f"{r.tool_name}: acl_bytes_sent mismatch")
        if not r.ok:
            fails.append(f"{r.tool_name}: call failed {r.error}")

    # Wire evidence: every captured HTTP request must carry identical hex header.
    wire = [e for e in captured if e.get("acl_hex")]
    print("WIRE_CAPTURE_COUNT", len(wire))
    for e in wire:
        print(f"WIRE path={e['path']} acl_hex={e['acl_hex']}")
        if e["acl_hex"] != acl.hex():
            fails.append(f"wire mismatch on {e['path']}")

    if len(wire) < 5:
        fails.append(f"expected >=5 wire captures, got {len(wire)}")

    # Prove no transformation: input == each sent == each wire header.
    for s in sent:
        if s != acl:
            fails.append("capture hook saw transformed ACL")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print("PASS")
    print(json.dumps({"tools": len(results), "wire_captures": len(wire), "acl_hex": acl.hex()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
