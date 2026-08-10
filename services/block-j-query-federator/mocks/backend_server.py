"""In-process mock backends for Blocks F / G / H used by Block J tests and compose."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

_TOKEN_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


@dataclass
class MockCorpus:
    """Shared corpus state for mock F/G/H handlers."""

    documents: List[Dict[str, Any]] = field(default_factory=list)
    kill_lexical: bool = False
    kill_vector: bool = False
    kill_graph: bool = False
    # When True, backends intentionally return restricted hits ignoring ACL
    # prefilter so Block J ACL post-check can be adversarially validated (J2).
    leak_restricted: bool = True

    def by_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        return [d for d in self.documents if d.get("tenant_id") == tenant_id]


corpus = MockCorpus()


def load_documents(docs: List[Dict[str, Any]]) -> None:
    corpus.documents = list(docs)
    corpus.kill_lexical = False
    corpus.kill_vector = False
    corpus.kill_graph = False


def _tokens(text: str) -> Set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _overlap(query: str, doc: Dict[str, Any]) -> float:
    q = _tokens(query)
    if not q:
        return 0.0
    blob = f"{doc.get('title', '')} {doc.get('body_text', '')}"
    d = _tokens(blob)
    return len(q & d) / len(q)


def _acl_allows(doc: Dict[str, Any], acl_terms: List[str]) -> bool:
    terms = set(acl_terms or [])
    doc_terms = set(doc.get("acl_filter_terms") or [])
    return bool(terms & doc_terms)


class LexicalRequest(BaseModel):
    query: str
    tenant_id: str
    user_id: str
    acl_terms: List[str]
    filters: Optional[Dict[str, Any]] = None
    facets: Optional[List[str]] = None
    from_: int = Field(0, alias="from")
    size: int = 20

    model_config = {"populate_by_name": True}


class VectorRequest(BaseModel):
    tenant_id: str
    principal_id: str
    acl_terms: List[str]
    query_embedding: List[float]
    top_k: int = 50
    model_version: Optional[str] = None


class GraphSignalsRequest(BaseModel):
    tenant_id: str
    principal_id: str
    document_ids: List[str]


def create_mock_app() -> FastAPI:
    """Build a FastAPI app exposing F/G/H-compatible routes."""
    app = FastAPI(title="Block J Mock Backends (F/G/H)")

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "kill": {
                "lexical": corpus.kill_lexical,
                "vector": corpus.kill_vector,
                "graph": corpus.kill_graph,
            },
        }

    @app.post("/_test/kill/{backend}")
    async def kill(backend: str, dead: bool = True):
        if backend == "lexical":
            corpus.kill_lexical = dead
        elif backend == "vector":
            corpus.kill_vector = dead
        elif backend == "graph":
            corpus.kill_graph = dead
        else:
            raise HTTPException(404, "unknown backend")
        return {"backend": backend, "dead": dead}

    @app.post("/search/lexical")
    @app.post("/api/v1/search/lexical")
    async def lexical_search(body: LexicalRequest):
        if corpus.kill_lexical:
            raise HTTPException(503, "lexical killed")
        hits = []
        # Include same-tenant docs plus cross-tenant restricted when leaking
        candidates = list(corpus.by_tenant(body.tenant_id))
        if corpus.leak_restricted:
            for doc in corpus.documents:
                if doc.get("restricted") and doc not in candidates:
                    candidates.append(doc)

        for doc in candidates:
            allowed = _acl_allows(doc, body.acl_terms)
            if not allowed and not (corpus.leak_restricted and doc.get("restricted")):
                continue
            ov = _overlap(body.query, doc)
            title_body = f"{doc.get('title', '')} {doc.get('body_text', '')}".lower()
            if ov <= 0 and body.query.lower() not in title_body:
                if not (doc.get("restricted") and corpus.leak_restricted):
                    continue
            base = float(doc.get("lexical_base_score") or 1.0)
            score = base * (0.4 + 0.6 * max(ov, 0.05))
            if body.query.lower() in (doc.get("title") or "").lower():
                score += 5.0
            hits.append(
                {
                    "document_id": doc["document_id"],
                    "score": score,
                    "title": doc.get("title") or "",
                    "snippet": doc.get("snippet") or (doc.get("body_text") or "")[:200],
                    "metadata": {
                        "source": doc.get("source"),
                        "object_type": doc.get("object_type"),
                        "tags": doc.get("tags"),
                    },
                }
            )
        hits.sort(key=lambda h: h["score"], reverse=True)
        page = hits[body.from_ : body.from_ + body.size]

        facets: Dict[str, List[Dict[str, Any]]] = {}
        if body.facets:
            for field in body.facets:
                counts: Dict[str, int] = {}
                for doc in corpus.by_tenant(body.tenant_id):
                    if not _acl_allows(doc, body.acl_terms):
                        continue
                    val = doc.get(field)
                    if isinstance(val, list):
                        for v in val:
                            counts[str(v)] = counts.get(str(v), 0) + 1
                    elif val is not None:
                        counts[str(val)] = counts.get(str(val), 0) + 1
                facets[field] = [
                    {"value": k, "count": v} for k, v in sorted(counts.items())
                ]

        return {"results": page, "facets": facets, "total": len(hits), "took_ms": 1.0}

    @app.post("/api/v1/search/vector")
    async def vector_search(body: VectorRequest):
        if corpus.kill_vector:
            raise HTTPException(503, "vector killed")
        q = body.query_embedding
        qnorm = math.sqrt(sum(x * x for x in q)) or 1.0
        hits = []
        candidates = list(corpus.by_tenant(body.tenant_id))
        if corpus.leak_restricted:
            for doc in corpus.documents:
                if doc.get("restricted") and doc not in candidates:
                    candidates.append(doc)

        from app.clients.embedding import EmbeddingClient

        embedder = EmbeddingClient(dimensions=len(q))
        for doc in candidates:
            allowed = _acl_allows(doc, body.acl_terms)
            if not allowed and not (corpus.leak_restricted and doc.get("restricted")):
                continue
            emb = embedder._embed_mock(
                f"{doc.get('title', '')} {doc.get('body_text', '')}"
            )
            dot = sum(a * b for a, b in zip(q, emb))
            score = dot / qnorm
            base = float(doc.get("vector_base_score") or 0.5)
            final = 0.7 * max(score, 0.0) + 0.3 * base
            hits.append(
                {
                    "chunk_id": f"chunk-{doc['document_id']}",
                    "document_id": doc["document_id"],
                    "score": final,
                    "model_version": body.model_version or "text-embedding-3-large",
                    "chunk_text": doc.get("body_text") or "",
                    "metadata": {"title": doc.get("title"), "source": doc.get("source")},
                }
            )
        hits.sort(key=lambda h: h["score"], reverse=True)
        return {
            "results": hits[: body.top_k],
            "model_versions_used": [body.model_version or "text-embedding-3-large"],
        }

    @app.post("/graph/signals")
    @app.post("/api/v1/graph/signals")
    async def graph_signals(body: GraphSignalsRequest, authorization: Optional[str] = Header(None)):
        if corpus.kill_graph:
            raise HTTPException(503, "graph killed")
        signals = {}
        by_id = {d["document_id"]: d for d in corpus.documents}
        for doc_id in body.document_ids:
            doc = by_id.get(doc_id)
            boost = float((doc or {}).get("graph_boost") or 0.0)
            # Ownership / collaboration nudge
            if doc and doc.get("owner") == body.principal_id:
                boost += 0.1
            signals[doc_id] = {
                "collaboration_boost": boost * 0.4,
                "ownership_boost": boost * 0.6,
                "total_boost": boost,
            }
        return {"signals": signals}

    return app


mock_app = create_mock_app()
