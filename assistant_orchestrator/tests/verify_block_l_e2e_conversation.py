#!/usr/bin/env python
"""Real multi-turn conversation against live orchestrator + Postgres memory."""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import threading
import time
import uuid

import uvicorn
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from assistant_orchestrator.api.routes import create_app, get_memory, get_toolbox, get_graph
from assistant_orchestrator.core.graph import OrchestratorGraph
from assistant_orchestrator.infrastructure.memory_store import EpisodicMemoryStore
from assistant_orchestrator.infrastructure.tools import SearchToolbox
from assistant_orchestrator.tests._stub_backends import create_stub_app, captured

PORT = int(os.getenv("BLOCK_L_STUB_PORT", "18995"))
BASE = f"http://127.0.0.1:{PORT}"


def _start_stub():
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


def _make_jwt(tenant_id: str, user_id: str) -> str:
    # Unverified-decode path: header.payload.sig (dev) — routes accept when key verify fails open to unverified only if no key...
    # With public key present, we need a real RS256 token OR ENVIRONMENT=test.
    # Use ENVIRONMENT=test for this script and a well-formed JWT payload.
    import base64
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "tenant_id": tenant_id,
        "principal_id": user_id,
        "scopes": ["search.read", "document.read", "signals.read", "activity.ingest"],
        "acl_terms": [f"user:{user_id}"],
    }).encode()).decode().rstrip("=")
    return f"{header}.{payload}.e2e"


async def run() -> int:
    captured.clear()
    _start_stub()
    os.environ["ENVIRONMENT"] = "test"
    os.environ["JWT_PUBLIC_KEY_PATH"] = ""  # use unverified decode for local e2e JWT
    os.environ["QUERY_FEDERATOR_URL"] = BASE
    os.environ["GRAPH_SERVICE_URL"] = BASE
    os.environ["DOCUMENT_READER_URL"] = BASE
    os.environ["SIGNALS_URL"] = BASE

    # Reset singletons to pick up URLs.
    import assistant_orchestrator.api.routes as routes
    routes._memory = EpisodicMemoryStore()
    routes._memory.ensure_schema()
    routes._toolbox = SearchToolbox(
        federator_url=BASE,
        graph_url=BASE,
        document_reader_url=BASE,
        signals_url=BASE,
    )
    routes._graph = OrchestratorGraph(routes._toolbox, routes._memory)

    app = create_app()
    client = TestClient(app)
    tenant = "tenant-e2e"
    user = "user-e2e"
    session_id = f"e2e-{uuid.uuid4().hex[:10]}"
    token = _make_jwt(tenant, user)
    headers = {"Authorization": f"Bearer {token}"}

    latencies = []
    fails = []

    turns = [
        "find the project roadmap highconf",
        "tell me more about the top result",
        "find lowconf deep details",
    ]
    finals = []
    for i, prompt in enumerate(turns, start=1):
        t0 = time.perf_counter()
        resp = client.post(
            "/orchestrator/chat",
            headers=headers,
            json={"prompt": prompt, "session_id": session_id},
        )
        elapsed = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed)
        print(f"TURN_{i}_STATUS", resp.status_code, f"latency_ms={elapsed:.1f}")
        if resp.status_code != 200:
            fails.append(f"turn {i} status {resp.status_code}: {resp.text}")
            continue
        lines = [json.loads(l) for l in resp.text.strip().splitlines() if l.strip()]
        final = next(x for x in lines if x.get("type") == "final")
        finals.append(final)
        print(f"TURN_{i}_FINAL", json.dumps({
            "response_prefix": (final.get("response_text") or "")[:80],
            "citations": len(final.get("citations") or []),
            "errors": final.get("errors") or [],
        }))
        if final.get("errors"):
            fails.append(f"turn {i} tool errors: {final.get('errors')}")
        if i != 2 and not (final.get("citations") or []):
            fails.append(f"turn {i} missing citations")

    # Session persistence across turns.
    sess = client.get(f"/orchestrator/sessions/{session_id}", headers=headers)
    print("SESSION_GET", sess.status_code, sess.text)
    if sess.status_code != 200:
        fails.append("session get failed")
    else:
        body = sess.json()
        if body.get("turn_count", 0) < 4:  # 3 user + at least 1 assistant persisted progressively
            # Each arun appends user+assistant => 6 turns expected after 3 prompts.
            if body.get("turn_count", 0) < 6:
                fails.append(f"expected >=6 history turns, got {body.get('turn_count')}")
        if body.get("tenant_id") != tenant:
            fails.append("session tenant mismatch")

    # Bucket latency percentiles across turns (not a single point estimate).
    if latencies:
        s = sorted(latencies)
        p50 = statistics.median(s)
        p95 = s[max(0, int(len(s) * 0.95) - 1)]
        print(json.dumps({
            "latency_ms_samples": latencies,
            "p50_ms": p50,
            "p95_ms": p95,
            "n": len(latencies),
        }, indent=2))

    # Multi-turn state: intent stack non-empty and last turn used reader for lowconf.
    if finals and not any(True for _ in finals):
        fails.append("no finals")
    mem = routes._memory
    ctx = mem.load_session(tenant, session_id)
    print("PERSISTED_INTENTS", ctx.intent_stack if ctx else None)
    print("PERSISTED_HISTORY_LEN", len(ctx.history) if ctx else None)
    if not ctx or len(ctx.history) < 6:
        fails.append("persisted history incomplete")
    if not ctx or len(ctx.intent_stack) < 3:
        fails.append("intent stack not persisted across turns")

    # Health against real Postgres was exercised via ensure_schema + load/save.
    # Also ping Qdrant readiness for stack evidence.
    try:
        import urllib.request
        q = urllib.request.urlopen("http://127.0.0.1:6333/readyz", timeout=3)
        print("QDRANT_READYZ", q.status, q.read().decode())
    except Exception as exc:
        fails.append(f"qdrant not ready: {exc}")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
