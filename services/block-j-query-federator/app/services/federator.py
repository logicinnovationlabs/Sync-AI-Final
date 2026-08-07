"""Query federator: fan-out, merge, ACL, graph signals, rank, paginate."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.embedding import EmbeddingClient
from app.clients.graph import GraphClient
from app.clients.lexical import LexicalClient
from app.clients.vector import VectorClient
from app.config import settings
from app.models import (
    BackendStatus,
    Candidate,
    Citation,
    FacetBucket,
    ResultItem,
    SearchRequest,
    SearchResponse,
    UserContext,
)
from app.services.permission import ACLStore, check_documents_access
from app.services.ranker import Ranker
from app.utils.metrics import metrics

logger = logging.getLogger(__name__)


class Federator:
    """Orchestrates hybrid retrieval across Blocks F / G / H."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        ranker: Ranker,
        embedding_client: Optional[EmbeddingClient] = None,
        lexical: Optional[LexicalClient] = None,
        vector: Optional[VectorClient] = None,
        graph: Optional[GraphClient] = None,
        acl_store: Optional[ACLStore] = None,
    ) -> None:
        self.http = http_client
        self.ranker = ranker
        self.embedding = embedding_client or EmbeddingClient(http_client)
        self.lexical = lexical or LexicalClient(http_client)
        self.vector = vector or VectorClient(http_client)
        self.graph = graph or GraphClient(http_client)
        self.acl_store = acl_store or ACLStore()

    async def search(
        self,
        request: SearchRequest,
        user_context: UserContext,
        *,
        authorization: Optional[str] = None,
        db_session: Optional[AsyncSession] = None,
    ) -> SearchResponse:
        """
        End-to-end federated search.

        Flow: embed → fan-out F/G → merge → ACL post-check → graph signals →
        rank → paginate. Gracefully degrades when individual backends fail.
        """
        started = time.perf_counter()
        acl_terms = user_context.build_acl_terms()
        backend_statuses: List[BackendStatus] = []

        # --- Fan-out (concurrent) ---
        lex_task = self._safe_lexical(request, user_context, acl_terms, authorization)
        vec_task = self._safe_vector(request, user_context, acl_terms, authorization)
        lex_result, vec_result = await asyncio.gather(lex_task, vec_task)

        backend_statuses.append(lex_result[1])
        backend_statuses.append(vec_result[1])

        if not lex_result[1].ok and not vec_result[1].ok:
            # Both primary retrieval backends failed → 500 (raised by caller path)
            metrics.incr("federator_all_backends_failed")
            raise RuntimeError("All retrieval backends failed")

        candidates = self._merge_candidates(lex_result[0], vec_result[0])

        # --- ACL post-check (batch) ---
        doc_ids = [c.document_id for c in candidates]
        allowed = await check_documents_access(
            doc_ids, user_context, db_session, store=self.acl_store.memory
        )
        candidates = [c for c in candidates if c.document_id in allowed]
        metrics.observe("acl_postcheck_filtered", len(doc_ids) - len(candidates))

        # --- Graph signals (optional, degraded) ---
        graph_payload, graph_status = await self._safe_graph(
            user_context, [c.document_id for c in candidates], authorization
        )
        backend_statuses.append(graph_status)
        if graph_payload:
            signals = graph_payload.get("signals") or {}
            for c in candidates:
                sig = signals.get(c.document_id) or {}
                boost = float(sig.get("total_boost", 0.0) or 0.0)
                c.graph_boost = boost
                if boost > 0 and "graph" not in c.sources:
                    c.sources.append("graph")

        # --- Rank ---
        ranked = self.ranker.rank(request.query, candidates)

        # --- Paginate ---
        total = len(ranked)
        page = ranked[request.from_ : request.from_ + request.size]
        facets = self._extract_facets(lex_result[0])

        took_ms = (time.perf_counter() - started) * 1000.0
        degraded = any(not b.ok for b in backend_statuses if b.name != "graph") or (
            not graph_status.ok and settings.enable_graph
        )
        # Graph-only failure still counts as degraded but is acceptable
        if not graph_status.ok and (lex_result[1].ok or vec_result[1].ok):
            degraded = True

        metrics.observe("search_latency_ms", took_ms)
        metrics.incr("search_requests")
        if degraded:
            metrics.incr("search_degraded")

        results = [self._to_result_item(c) for c in page]
        return SearchResponse(
            results=results,
            facets=facets,
            total=total,
            took_ms=took_ms,
            degraded=degraded,
            backends=backend_statuses,
            query=request.query if request.debug else None,
        )

    async def _safe_lexical(
        self,
        request: SearchRequest,
        user: UserContext,
        acl_terms: List[str],
        authorization: Optional[str],
    ) -> Tuple[Dict[str, Any], BackendStatus]:
        if not settings.enable_lexical:
            return {}, BackendStatus(name="lexical", ok=False, error="disabled")
        try:
            data = await self.lexical.search(
                query=request.query,
                tenant_id=user.tenant_id,
                user_id=user.principal_id,
                acl_terms=acl_terms,
                filters=request.filters.model_dump(exclude_none=True) if request.filters else None,
                facets=request.facets,
                size=settings.default_candidate_size,
                authorization=authorization,
            )
            hits = data.get("results") or []
            return data, BackendStatus(
                name="lexical",
                ok=True,
                latency_ms=float(data.get("latency_ms", 0.0)),
                hit_count=len(hits),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lexical backend failed: %s", exc)
            metrics.incr("backend_errors", backend="lexical")
            return {}, BackendStatus(name="lexical", ok=False, error=str(exc))

    async def _safe_vector(
        self,
        request: SearchRequest,
        user: UserContext,
        acl_terms: List[str],
        authorization: Optional[str],
    ) -> Tuple[Dict[str, Any], BackendStatus]:
        if not settings.enable_vector:
            return {}, BackendStatus(name="vector", ok=False, error="disabled")
        try:
            embedding = request.query_embedding
            if embedding is None:
                embedding = await self.embedding.embed(request.query)
            data = await self.vector.search(
                tenant_id=user.tenant_id,
                principal_id=user.principal_id,
                acl_terms=acl_terms,
                query_embedding=embedding,
                top_k=settings.default_candidate_size,
                model_version=settings.embedding_model_version,
                authorization=authorization,
            )
            hits = data.get("results") or []
            return data, BackendStatus(
                name="vector",
                ok=True,
                latency_ms=float(data.get("latency_ms", 0.0)),
                hit_count=len(hits),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vector backend failed: %s", exc)
            metrics.incr("backend_errors", backend="vector")
            return {}, BackendStatus(name="vector", ok=False, error=str(exc))

    async def _safe_graph(
        self,
        user: UserContext,
        document_ids: List[str],
        authorization: Optional[str],
    ) -> Tuple[Dict[str, Any], BackendStatus]:
        if not settings.enable_graph:
            return {}, BackendStatus(name="graph", ok=False, error="disabled")
        if not document_ids:
            return {"signals": {}}, BackendStatus(name="graph", ok=True, hit_count=0)
        try:
            data = await self.graph.fetch_signals(
                tenant_id=user.tenant_id,
                principal_id=user.principal_id,
                document_ids=document_ids,
                authorization=authorization,
            )
            return data, BackendStatus(
                name="graph",
                ok=True,
                latency_ms=float(data.get("latency_ms", 0.0)),
                hit_count=len(data.get("signals") or {}),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Graph backend failed: %s", exc)
            metrics.incr("backend_errors", backend="graph")
            return {}, BackendStatus(name="graph", ok=False, error=str(exc))

    def _merge_candidates(
        self,
        lexical_payload: Dict[str, Any],
        vector_payload: Dict[str, Any],
    ) -> List[Candidate]:
        """Deduplicate by document_id; keep best snippet; accumulate scores."""
        by_id: Dict[str, Candidate] = {}

        for hit in lexical_payload.get("results") or []:
            doc_id = str(hit.get("document_id") or "")
            if not doc_id:
                continue
            score = float(hit.get("score") or 0.0)
            existing = by_id.get(doc_id)
            if existing is None:
                by_id[doc_id] = Candidate(
                    document_id=doc_id,
                    title=str(hit.get("title") or ""),
                    snippet=str(hit.get("snippet") or ""),
                    lexical_score=score,
                    sources=["lexical"],
                    metadata=dict(hit.get("metadata") or {}),
                )
            else:
                existing.lexical_score = max(existing.lexical_score, score)
                if "lexical" not in existing.sources:
                    existing.sources.append("lexical")
                snippet = str(hit.get("snippet") or "")
                if len(snippet) > len(existing.snippet):
                    existing.snippet = snippet
                if hit.get("title") and not existing.title:
                    existing.title = str(hit["title"])
                meta = hit.get("metadata") or {}
                existing.metadata.update(meta)

        for hit in vector_payload.get("results") or []:
            doc_id = str(hit.get("document_id") or "")
            if not doc_id:
                continue
            score = float(hit.get("score") or 0.0)
            chunk_text = str(hit.get("chunk_text") or "")
            meta = dict(hit.get("metadata") or {})
            title = str(meta.get("title") or "")
            existing = by_id.get(doc_id)
            if existing is None:
                by_id[doc_id] = Candidate(
                    document_id=doc_id,
                    title=title,
                    snippet=chunk_text[:240],
                    vector_score=score,
                    sources=["vector"],
                    metadata=meta,
                    chunk_text=chunk_text,
                )
            else:
                existing.vector_score = max(existing.vector_score, score)
                if "vector" not in existing.sources:
                    existing.sources.append("vector")
                if chunk_text and (
                    not existing.snippet or len(chunk_text) > len(existing.snippet)
                ):
                    if not existing.snippet:
                        existing.snippet = chunk_text[:240]
                    existing.chunk_text = chunk_text
                if title and not existing.title:
                    existing.title = title
                existing.metadata.update(meta)

        return list(by_id.values())

    def _extract_facets(
        self, lexical_payload: Dict[str, Any]
    ) -> Dict[str, List[FacetBucket]]:
        raw = lexical_payload.get("facets") or {}
        out: Dict[str, List[FacetBucket]] = {}
        for field, buckets in raw.items():
            parsed: List[FacetBucket] = []
            for b in buckets or []:
                if isinstance(b, dict):
                    parsed.append(
                        FacetBucket(
                            value=str(b.get("value", "")),
                            count=int(b.get("count", 0)),
                        )
                    )
            out[field] = parsed
        return out

    def _to_result_item(self, c: Candidate) -> ResultItem:
        final_score = (
            c.rerank_score
            if c.rerank_score is not None
            else c.fusion_score
        )
        citation = Citation(
            document_id=c.document_id,
            title=c.title or None,
            source=(c.metadata or {}).get("source"),
            url=(c.metadata or {}).get("url"),
        )
        return ResultItem(
            document_id=c.document_id,
            score=float(final_score or 0.0),
            title=c.title,
            snippet=c.snippet,
            sources=list(c.sources),
            lexical_score=c.lexical_score or None,
            vector_score=c.vector_score or None,
            graph_boost=c.graph_boost or None,
            fusion_score=c.fusion_score or None,
            rerank_score=c.rerank_score,
            metadata=c.metadata or None,
            citations=[citation],
        )
