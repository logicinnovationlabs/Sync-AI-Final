"""In-process + CLI contract mock server for provisional Block Z-O tests."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import jwt
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

JWT_SECRET = os.environ.get("JWT_TEST_SECRET", "test-suite-hs256-secret-32b-min!!")
JWT_ALG = "HS256"
_REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_PATH = Path(os.environ.get("FIXTURES_PATH", str(_REPO_ROOT / "fixtures")))


class FixtureStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: Dict[str, Any] = {}
        self.revoked_jtis: Set[str] = set()
        self.scim_runs: List[Dict[str, Any]] = []
        self.checkpoints: Dict[str, str] = {}
        self.audit_events: List[Dict[str, Any]] = []
        self.keys_version = 1
        self.reload()

    def reload(self) -> None:
        for fp in self.path.glob("*.json"):
            with open(fp, encoding="utf-8") as f:
                self.data[fp.stem] = json.load(f)

    def documents(self) -> List[Dict]:
        return list(self.data.get("documents", {}).get("documents", []))

    def principals(self) -> List[Dict]:
        return list(self.data.get("principals", {}).get("principals", []))

    def groups(self) -> List[Dict]:
        return list(self.data.get("groups", {}).get("groups", []))

    def acl_entries(self) -> List[Dict]:
        return list(self.data.get("acl_matrix", {}).get("entries", []))

    def edges(self) -> List[Dict]:
        return list(self.data.get("graph_edges", {}).get("edges", []))

    def identities(self) -> List[Dict]:
        return list(self.data.get("multi_source_identities", {}).get("identities", []))

    def redteam(self) -> List[Dict]:
        return list(self.data.get("acl_redteam_cases", {}).get("cases", []))

    def labels(self) -> List[Dict]:
        return list(self.data.get("relevance_labels", {}).get("labels", []))

    def crawl(self) -> Dict:
        return dict(self.data.get("crawl_expectations", {}))

    def allowed_docs(self, principal_id: str) -> List[Dict]:
        allowed = {
            e["document_id"]
            for e in self.acl_entries()
            if e.get("principal_id") == principal_id
        }
        return [d for d in self.documents() if d["id"] in allowed]

    def principal_by_id(self, principal_id: str) -> Optional[Dict]:
        for p in self.principals():
            if p["id"] == principal_id:
                return p
        return None

    def audit(self, event_type: str, **kwargs: Any) -> None:
        self.audit_events.append(
            {
                "id": str(uuid.uuid4()),
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **kwargs,
            }
        )


STORE = FixtureStore(FIXTURES_PATH)
app = FastAPI(title="SynQ Contract Mock Server", version="1.0.0")


def _issue_token(
    principal_id: str,
    tenant_id: str,
    scopes: Optional[List[str]] = None,
    ttl_seconds: int = 3600,
) -> Dict[str, Any]:
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload = {
        "sub": principal_id,
        "tenant_id": tenant_id,
        "scopes": scopes or ["search.read", "document.read"],
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
    return {"access_token": token, "token_type": "bearer", "expires_in": ttl_seconds, "jti": jti}


def _decode_auth(authorization: Optional[str]) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"error": {"code": "missing_token", "message": "Bearer required"}})
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail={"error": {"code": "invalid_token", "message": str(exc)}}) from exc
    if payload.get("jti") in STORE.revoked_jtis:
        raise HTTPException(status_code=401, detail={"error": {"code": "revoked", "message": "token revoked"}})
    return payload


def _require_tenant(payload: Dict[str, Any], x_tenant_id: Optional[str]) -> None:
    if x_tenant_id and x_tenant_id != payload.get("tenant_id"):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "tenant_mismatch", "message": "X-Tenant-ID does not match token"}},
        )


def _require_scope(payload: Dict[str, Any], scope: str) -> None:
    scopes = payload.get("scopes") or []
    if scope not in scopes:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "insufficient_scope", "message": f"missing scope {scope}"}},
        )


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "fixtures_version": STORE.data.get("MANIFEST", {}).get("version", "v1")}


@app.post("/oauth/token")
async def oauth_token(request: Request) -> Dict[str, Any]:
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    principal_id = body.get("principal_id") or body.get("username") or "principal-alice"
    principal = STORE.principal_by_id(principal_id)
    if not principal:
        # allow synthetic tenants for A1 binding tests
        tenant_id = body.get("tenant_id", "tenant-a")
        scopes = body.get("scopes") or ["search.read"]
        return _issue_token(principal_id, tenant_id, scopes)
    return _issue_token(principal["id"], principal["tenant_id"], principal.get("scopes"))


@app.post("/oauth/revoke")
async def oauth_revoke(request: Request, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    jti = body.get("jti")
    if not jti and authorization:
        try:
            payload = _decode_auth(authorization)
            jti = payload.get("jti")
        except HTTPException:
            pass
    if jti:
        STORE.revoked_jtis.add(jti)
        STORE.audit("token_revoke", jti=jti)
    return {"revoked": True, "latency_budget_s": 60}


@app.get("/api/v1/me")
def me(
    authorization: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    _require_tenant(payload, x_tenant_id)
    return {
        "principal_id": payload.get("sub"),
        "tenant_id": payload.get("tenant_id"),
        "scopes": payload.get("scopes", []),
    }


@app.get("/api/v1/principals")
def list_principals(
    authorization: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    _require_tenant(payload, x_tenant_id)
    tenant = payload.get("tenant_id")
    items = [p for p in STORE.principals() if p["tenant_id"] == tenant]
    return {"principals": items}


@app.post("/scim/sync")
async def scim_sync(request: Request) -> Dict[str, Any]:
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    # Deterministic principal ids from fixtures (idempotent)
    mapping = {p["external_id"]: p["id"] for p in STORE.principals()}
    users = body.get("users") or [
        {"external_id": p["external_id"], "email": p["email"]} for p in STORE.principals()
    ]
    results = []
    for u in users:
        ext = u.get("external_id")
        pid = mapping.get(ext) or f"principal-{ext}"
        results.append({"external_id": ext, "principal_id": pid})
    STORE.scim_runs.append({"results": results, "ts": time.time()})
    STORE.audit("scim_sync", count=len(results))
    return {"synced": len(results), "principals": results, "idempotent": True}


@app.get("/api/v1/scoped/search")
def scoped_search(
    authorization: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    _require_tenant(payload, x_tenant_id)
    _require_scope(payload, "search.read")
    return {"ok": True}


@app.get("/api/v1/scoped/documents")
def scoped_documents(
    authorization: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    _require_tenant(payload, x_tenant_id)
    _require_scope(payload, "document.read")
    return {"ok": True}


@app.get("/api/v1/scoped/admin/audit")
def scoped_admin_audit(
    authorization: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    _require_tenant(payload, x_tenant_id)
    _require_scope(payload, "admin.audit.read")
    return {"ok": True}


@app.get("/connectors")
def connectors() -> Dict[str, Any]:
    return {"connectors": ["google_drive", "google_gmail"]}


@app.post("/connectors/google-drive/crawl")
async def crawl_drive() -> Dict[str, Any]:
    docs = [d for d in STORE.documents() if d.get("source") == "google_drive"]
    return {
        "crawl_id": "crawl-drive-1",
        "expected": len(docs),
        "ingested": len(docs),
        "objects": [{"id": d["id"], "delta_type": d.get("delta_type", "created")} for d in docs],
        "credentials_leaked": False,
    }


@app.post("/connectors/google-gmail/crawl")
async def crawl_gmail() -> Dict[str, Any]:
    docs = [d for d in STORE.documents() if d.get("source") == "google_gmail"]
    return {
        "crawl_id": "crawl-gmail-1",
        "expected": len(docs),
        "ingested": len(docs),
        "objects": [{"id": d["id"], "delta_type": d.get("delta_type", "created")} for d in docs],
        "credentials_leaked": False,
    }


@app.get("/crawls/{crawl_id}")
def crawl_status(crawl_id: str) -> Dict[str, Any]:
    return {"crawl_id": crawl_id, "status": "complete", "rate_limit_retries": STORE.crawl().get("rate_limit_retries", 3)}


@app.get("/ingested-objects")
def ingested_objects() -> Dict[str, Any]:
    return {"objects": [{"id": d["id"], "source": d["source"], "checkpoint": d.get("checkpoint")} for d in STORE.documents()]}


@app.post("/connectors/checkpoint")
async def checkpoint(request: Request) -> Dict[str, Any]:
    body = await request.json()
    source = body.get("source", "google_drive")
    cp = body.get("checkpoint") or f"cp-{source}-resume"
    STORE.checkpoints[source] = cp
    return {"resumed_from": cp, "source": source, "ok": True}


@app.post("/identity/resolve")
async def identity_resolve(request: Request) -> Dict[str, Any]:
    body = await request.json()
    external_id = body.get("external_id")
    source_type = body.get("source_type")
    resolved = []
    for identity in STORE.identities():
        for src in identity.get("sources", []):
            if src.get("external_id") == external_id and (not source_type or src.get("source_type") == source_type):
                resolved.append({"principal_id": identity["principal_id"], "external_id": external_id})
    return {"resolved": resolved, "confidence": 1.0 if resolved else 0.0}


@app.post("/normalize")
async def normalize(request: Request) -> Dict[str, Any]:
    body = await request.json()
    # Deterministic normalize: sort keys + stable id
    doc = body.get("document") or {}
    norm = {
        "id": doc.get("id"),
        "tenant_id": doc.get("tenant_id"),
        "title": doc.get("title"),
        "body": doc.get("body"),
        "acl": sorted(doc.get("acl") or []),
    }
    return {"normalized": norm, "hash": str(hash(json.dumps(norm, sort_keys=True)))}


@app.get("/storage/health")
def storage_health() -> Dict[str, Any]:
    return {"status": "ok", "keys_version": STORE.keys_version}


@app.post("/tenants/{tenant_id}/provision")
def provision(tenant_id: str) -> Dict[str, Any]:
    start = time.time()
    # simulate fast provisional provision
    elapsed = (time.time() - start) * 1000
    STORE.audit("provision", tenant_id=tenant_id, elapsed_ms=elapsed)
    return {"tenant_id": tenant_id, "provisioned": True, "elapsed_ms": elapsed}


@app.post("/tenants/{tenant_id}/backup")
def backup(tenant_id: str) -> Dict[str, Any]:
    docs = [d for d in STORE.documents() if d["tenant_id"] == tenant_id]
    return {"tenant_id": tenant_id, "backup_id": f"bak-{tenant_id}", "document_count": len(docs)}


@app.post("/tenants/{tenant_id}/restore")
def restore(tenant_id: str) -> Dict[str, Any]:
    docs = [d for d in STORE.documents() if d["tenant_id"] == tenant_id]
    return {"tenant_id": tenant_id, "restored": True, "document_count": len(docs)}


@app.post("/keys/rotate")
def rotate_keys() -> Dict[str, Any]:
    STORE.keys_version += 1
    return {"keys_version": STORE.keys_version, "rotated": True}


@app.post("/embed")
async def embed(request: Request) -> Dict[str, Any]:
    body = await request.json()
    doc_id = body.get("document_id")
    doc = next((d for d in STORE.documents() if d["id"] == doc_id), None)
    chunks = (doc or {}).get("chunks") or [f"chk-{doc_id}-1"]
    return {"document_id": doc_id, "chunks": [{"id": c, "embedding_dim": 8, "vector": [0.1] * 8} for c in chunks]}


@app.post("/reembed")
async def reembed(request: Request) -> Dict[str, Any]:
    body = await request.json()
    return {"document_id": body.get("document_id"), "triggered": True, "reason": body.get("reason", "model_bump")}


@app.get("/chunks/{doc_id}")
def get_chunks(doc_id: str) -> Dict[str, Any]:
    doc = next((d for d in STORE.documents() if d["id"] == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    return {"document_id": doc_id, "chunks": doc.get("chunks", [])}


def _acl_filter_hits(principal_id: str, query: str) -> List[Dict]:
    q = (query or "").lower().strip()
    hits = []
    for d in STORE.allowed_docs(principal_id):
        hay = f"{d.get('title','')} {d.get('body','')}".lower()
        if not q:
            score = 0.1
        elif q in hay:
            score = 1.0
        elif any(tok and tok in hay for tok in q.split()):
            score = 0.5
        else:
            continue
        hits.append({"document_id": d["id"], "tenant_id": d["tenant_id"], "score": score, "title": d["title"]})
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits


@app.post("/search/lexical")
async def search_lexical(request: Request, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    body = await request.json()
    hits = _acl_filter_hits(payload["sub"], body.get("query", ""))
    # facet accuracy: source facets only for visible docs
    facets = {}
    for d in STORE.allowed_docs(payload["sub"]):
        facets[d["source"]] = facets.get(d["source"], 0) + 1
    return {"hits": hits[:10], "facets": facets, "took_ms": 5, "index_lag_ms": 0}


@app.post("/search/vector")
async def search_vector(request: Request, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    body = await request.json()
    hits = _acl_filter_hits(payload["sub"], body.get("query", ""))
    return {"hits": hits[:10], "model_version": body.get("model_version", "v1"), "took_ms": 8}


@app.post("/graph/traverse")
async def graph_traverse(request: Request, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    body = await request.json()
    start = body.get("start") or payload["sub"]
    depth = int(body.get("depth", 1))
    edges = [e for e in STORE.edges() if e["source"] == start or e["target"] == start]
    # tenant isolation: drop edges to docs outside principal tenant
    principal = STORE.principal_by_id(payload["sub"])
    tenant = (principal or {}).get("tenant_id")
    filtered = []
    doc_map = {d["id"]: d for d in STORE.documents()}
    for e in edges:
        for node in (e["source"], e["target"]):
            if node in doc_map and doc_map[node]["tenant_id"] != tenant:
                break
        else:
            filtered.append(e)
    return {"start": start, "depth": depth, "edges": filtered, "took_ms": 3}


@app.post("/graph/merge")
async def graph_merge(request: Request) -> Dict[str, Any]:
    body = await request.json()
    return {"merged": True, "nodes": body.get("nodes", []), "integrity": "ok"}


@app.post("/graph/split")
async def graph_split(request: Request) -> Dict[str, Any]:
    body = await request.json()
    return {"split": True, "node": body.get("node"), "integrity": "ok"}


@app.get("/signals/user/{user_id}")
def signals(user_id: str, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    principal = STORE.principal_by_id(payload["sub"])
    if user_id != payload["sub"] and (principal or {}).get("tenant_id"):
        # cross-user same tenant allowed for mock; cross-tenant blocked
        other = STORE.principal_by_id(user_id)
        if other and other["tenant_id"] != principal["tenant_id"]:
            raise HTTPException(status_code=403, detail={"error": {"code": "tenant_isolation", "message": "cross-tenant"}})
    return {
        "user_id": user_id,
        "signals": [{"type": "click", "document_id": "doc-roadmap", "freshness_s": 30}],
        "ranking_boost": 0.15,
    }


@app.post("/api/v1/search")
async def federated_search(request: Request, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    body = await request.json()
    query = body.get("query", "")
    hits = _acl_filter_hits(payload["sub"], query)
    # graceful degradation flag
    degraded = bool(body.get("force_degrade"))
    return {
        "hits": hits[:10],
        "took_ms": 12 if not degraded else 40,
        "degraded": degraded,
        "sources": ["lexical", "vector"] if not degraded else ["lexical"],
    }


@app.post("/api/v1/read")
async def read_doc(request: Request, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    body = await request.json()
    doc_id = body.get("document_id")
    allowed = {d["id"] for d in STORE.allowed_docs(payload["sub"])}
    if doc_id not in allowed:
        raise HTTPException(status_code=403, detail={"error": {"code": "acl_denied", "message": "no access"}})
    doc = next(d for d in STORE.documents() if d["id"] == doc_id)
    return {"document_id": doc_id, "title": doc["title"], "body": doc["body"], "took_ms": 10, "complete": True}


@app.post("/api/v1/assistant/chat")
async def assistant_chat(request: Request, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    body = await request.json()
    query = body.get("query", "")
    hits = _acl_filter_hits(payload["sub"], query)
    if not hits:
        return {
            "answer": "I cannot access documents for that query.",
            "refused": True,
            "citations": [],
            "took_ms": 20,
        }
    top = hits[0]
    doc = next(d for d in STORE.documents() if d["id"] == top["document_id"])
    return {
        "answer": f"Based on {doc['title']}: {doc['body'][:120]}",
        "refused": False,
        "citations": [{"document_id": doc["id"], "quote": doc["body"][:80]}],
        "took_ms": 25,
    }


@app.get("/mcp/tools")
def mcp_tools() -> Dict[str, Any]:
    return {
        "tools": [
            {
                "name": "search",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "tenant_id": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "read_document",
                "input_schema": {
                    "type": "object",
                    "properties": {"document_id": {"type": "string"}},
                    "required": ["document_id"],
                },
            },
        ]
    }


@app.post("/mcp/call")
async def mcp_call(request: Request, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    body = await request.json()
    tool = body.get("tool")
    args = body.get("arguments") or {}
    # rate limit simulation: allow 100
    STORE.audit("mcp_call", tool=tool, principal=payload["sub"])
    if tool == "search":
        hits = _acl_filter_hits(payload["sub"], args.get("query", ""))
        return {"result": hits, "auth_principal": payload["sub"], "tenant_id": payload["tenant_id"]}
    if tool == "read_document":
        allowed = {d["id"] for d in STORE.allowed_docs(payload["sub"])}
        doc_id = args.get("document_id")
        if doc_id not in allowed:
            raise HTTPException(status_code=403, detail={"error": {"code": "acl_denied", "message": "no access"}})
        return {"result": {"document_id": doc_id}, "auth_principal": payload["sub"], "tenant_id": payload["tenant_id"]}
    raise HTTPException(status_code=400, detail="unknown tool")


@app.get("/admin/audit")
def admin_audit(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    _require_scope(payload, "admin.audit.read")
    return {"events": STORE.audit_events}


@app.get("/admin/config")
def admin_config(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    payload = _decode_auth(authorization)
    # no secrets in config surface
    return {
        "phase": "provisional",
        "jwt_alg": JWT_ALG,
        "secrets_present": False,
        "safe_keys": ["MOCK_BASE_PORT", "FIXTURES_VERSION"],
    }


@app.get("/metrics")
def metrics() -> Dict[str, Any]:
    # bounded cardinality labels
    return {
        "metrics": [
            {"name": "http_requests_total", "labels": {"route": "/api/v1/search", "status": "200"}, "value": 1},
            {"name": "search_latency_ms", "labels": {"backend": "lexical"}, "value": 5},
        ],
        "cardinality_ok": True,
    }


@app.get("/traces")
def traces() -> Dict[str, Any]:
    return {
        "traces": [
            {
                "trace_id": "trace-demo",
                "spans": [
                    {"name": "auth", "trace_id": "trace-demo"},
                    {"name": "search", "trace_id": "trace-demo"},
                ],
            }
        ]
    }


class InProcessServer:
    def __init__(self, port: int):
        self.port = port
        self._thread: Optional[threading.Thread] = None
        self._server: Optional[uvicorn.Server] = None

    def start(self) -> None:
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)

        def run() -> None:
            assert self._server is not None
            self._server.run()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        # wait until ready
        deadline = time.time() + 10
        import urllib.request

        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=0.5) as resp:
                    if resp.status == 200:
                        return
            except Exception:
                time.sleep(0.05)
        raise RuntimeError(f"Mock server failed to start on {self.port}")

    def shutdown(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)


def start_inprocess_server(port: int = 10001) -> InProcessServer:
    server = InProcessServer(port)
    server.start()
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="SynQ contract mock server")
    parser.add_argument("--port", type=int, default=10001)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
