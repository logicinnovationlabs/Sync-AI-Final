"""Local HTTP backends that record ACL headers for Block L verification.

These stand in for downstream HTTP services (J/H/K/I) so pass-through and boost
logic can be proven against a real network stack when full block containers are
unavailable on colliding ports. Verification still uses real Postgres :5433.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI, Request

captured: List[Dict[str, Any]] = []


def create_stub_app() -> FastAPI:
    app = FastAPI(title="block-l-stub-backends")

    @app.middleware("http")
    async def capture_acl(request: Request, call_next):
        body = await request.body()
        entry = {
            "path": request.url.path,
            "method": request.method,
            "acl_hex": request.headers.get("x-acl-compiled-filter"),
            "authorization": request.headers.get("authorization"),
            "body": body.decode("utf-8", errors="replace"),
        }
        captured.append(entry)

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive  # type: ignore[attr-defined]
        return await call_next(request)

    @app.post("/api/v1/search")
    async def search(request: Request):
        payload = await request.json()
        mode = payload.get("orchestrator_mode", "lexical")
        q = (payload.get("query") or "").lower()
        if "highconf" in q:
            score = 0.92
        elif "lowconf" in q:
            score = 0.25
        else:
            score = 0.55 if mode == "lexical" else 0.48
        results = [
            {
                "document_id": "doc-alpha",
                "score": score,
                "title": "Alpha Spec",
                "snippet": "alpha content about roadmap",
                "sources": [mode],
            },
            {
                "document_id": "doc-beta",
                "score": max(0.05, score - 0.1),
                "title": "Beta Notes",
                "snippet": "beta content",
                "sources": [mode],
            },
            {
                "document_id": "doc-gamma",
                "score": max(0.02, score - 0.2),
                "title": "Gamma Plan",
                "snippet": "gamma content",
                "sources": [mode],
            },
        ]
        return {"results": results, "total": len(results), "took_ms": 3, "backends": ["stub"]}

    @app.post("/graph/traverse")
    async def traverse(request: Request):
        return {"nodes": [], "relationships": [], "start_node_id": "n1", "depth": 1}

    @app.get("/api/v1/document/{doc_id}")
    async def read_doc(doc_id: str):
        return {
            "document_id": doc_id,
            "tenant_id": "tenant-a",
            "title": f"Full {doc_id}",
            "body": f"DEEP_EXTRACTED_BODY for {doc_id} " + ("x" * 200),
            "structured_metadata": {},
        }

    @app.get("/signals/user/{user_id}")
    async def user_signals(user_id: str, request: Request):
        if user_id.endswith("-boosted"):
            return {
                "user_id": user_id,
                "tenant_id": "tenant-a",
                "signals": {
                    "top_viewed_docs": [
                        {"document_id": "doc-beta", "score": 1.0, "event_time": "2026-08-11T10:00:00Z"}
                    ],
                    "recent_views": [
                        {"document_id": "doc-beta", "event_time": "2026-08-11T10:00:00Z"}
                    ],
                },
                "freshness_s": 1,
            }
        return {
            "user_id": user_id,
            "tenant_id": "tenant-a",
            "signals": {"top_viewed_docs": [], "recent_views": []},
            "freshness_s": 1,
        }

    @app.post("/activity/ingest")
    async def ingest(request: Request):
        return {"ingested": 1, "already_processed": 0, "failed": []}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/_captured")
    async def get_captured():
        return {"captured": captured}

    @app.post("/_captured/clear")
    async def clear_captured():
        captured.clear()
        return {"ok": True}

    return app
