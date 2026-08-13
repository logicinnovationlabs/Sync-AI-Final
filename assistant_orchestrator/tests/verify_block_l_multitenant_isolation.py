#!/usr/bin/env python
"""Prove no session/memory/tool-result leak across distinct tenant IDs."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import uuid

import uvicorn

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from assistant_orchestrator.core.graph import OrchestratorGraph
from assistant_orchestrator.domain.models import OrchestratorRequest
from assistant_orchestrator.infrastructure.memory_store import EpisodicMemoryStore
from assistant_orchestrator.infrastructure.tools import SearchToolbox, encode_acl_terms
from assistant_orchestrator.tests._stub_backends import create_stub_app, captured

PORT = int(os.getenv("BLOCK_L_STUB_PORT", "18994"))
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


async def run() -> int:
    captured.clear()
    _start_server()
    mem = EpisodicMemoryStore()
    mem.ensure_schema()
    toolbox = SearchToolbox(
        federator_url=BASE,
        graph_url=BASE,
        document_reader_url=BASE,
        signals_url=BASE,
    )
    graph = OrchestratorGraph(toolbox, mem)

    session_id = f"shared-session-{uuid.uuid4().hex[:8]}"
    tenant_a = "tenant-A-iso"
    tenant_b = "tenant-B-iso"

    # Same session_id string, different tenants — must not collide.
    ra = await graph.arun(
        OrchestratorRequest(
            tenant_id=tenant_a,
            user_id="user-a",
            session_id=session_id,
            prompt="find roadmap for tenant A secret-alpha-token",
        ),
        acl_compiled_filter=encode_acl_terms(["user:user-a"]),
        authorization="Bearer a",
    )
    rb = await graph.arun(
        OrchestratorRequest(
            tenant_id=tenant_b,
            user_id="user-b",
            session_id=session_id,
            prompt="find roadmap for tenant B secret-beta-token",
        ),
        acl_compiled_filter=encode_acl_terms(["user:user-b"]),
        authorization="Bearer b",
    )

    sa = mem.load_session(tenant_a, session_id)
    sb = mem.load_session(tenant_b, session_id)
    # Cross-tenant load must not return the other tenant's session.
    cross = mem.load_session(tenant_a, session_id)
    mem.put_memory(tenant_a, "user-a", "pref", {"note": "alpha-only"})
    mem.put_memory(tenant_b, "user-b", "pref", {"note": "beta-only"})
    ma = mem.get_memory(tenant_a, "user-a", "pref")
    mb = mem.get_memory(tenant_b, "user-b", "pref")
    leak_ab = mem.get_memory(tenant_a, "user-b", "pref")
    leak_ba = mem.get_memory(tenant_b, "user-a", "pref")

    await toolbox.aclose()

    print("SESSION_A_TURNS", len(sa.history) if sa else None)
    print("SESSION_B_TURNS", len(sb.history) if sb else None)
    print("MEMORY_A", ma)
    print("MEMORY_B", mb)
    print("SESSIONS_A", mem.list_sessions_for_tenant(tenant_a))
    print("SESSIONS_B", mem.list_sessions_for_tenant(tenant_b))

    fails = []
    if sa is None or sb is None:
        fails.append("missing tenant session")
    if sa and sb:
        if sa.tenant_id != tenant_a or sb.tenant_id != tenant_b:
            fails.append("session tenant_id mismatch")
        a_text = " ".join(t.content for t in sa.history)
        b_text = " ".join(t.content for t in sb.history)
        if "secret-beta-token" in a_text:
            fails.append("tenant A session leaked tenant B prompt")
        if "secret-alpha-token" in b_text:
            fails.append("tenant B session leaked tenant A prompt")
        if sa.user_id == sb.user_id:
            fails.append("user_ids unexpectedly identical across tenants")
    if cross and cross.tenant_id != tenant_a:
        fails.append("cross load returned wrong tenant")
    if ma != {"note": "alpha-only"}:
        fails.append(f"tenant A memory wrong: {ma}")
    if mb != {"note": "beta-only"}:
        fails.append(f"tenant B memory wrong: {mb}")
    if leak_ab is not None or leak_ba is not None:
        fails.append(f"cross-tenant memory leak: {leak_ab} {leak_ba}")
    if session_id not in mem.list_sessions_for_tenant(tenant_a):
        fails.append("tenant A session list missing session")
    if session_id not in mem.list_sessions_for_tenant(tenant_b):
        fails.append("tenant B session list missing session")
    # Tool ACL filters must remain tenant-specific opaque bytes.
    a_acl = encode_acl_terms(["user:user-a"]).hex()
    b_acl = encode_acl_terms(["user:user-b"]).hex()
    wire_a = [e for e in captured if e.get("acl_hex") == a_acl]
    wire_b = [e for e in captured if e.get("acl_hex") == b_acl]
    print("WIRE_A", len(wire_a), "WIRE_B", len(wire_b))
    if not wire_a or not wire_b:
        fails.append("missing per-tenant ACL wire captures")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print("PASS")
    print(json.dumps({"session_id": session_id, "tenant_a": tenant_a, "tenant_b": tenant_b}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
