"""RAG Debug Trace — per-query pipeline instrumentation.

Rule #2 from the RAG Architecture Spec.  When ``RAG_DEBUG_TRACE=true``,
every retrieval→generation stage is logged with actual data so a human can
see where relevant content disappears.

**Rule #5 reminder:**  Once the trace identifies the failing layer,
implement only the minimal fix for that layer.  Do not combine hybrid search,
reranking, and query rewriting in a single change — each is a separate
before/after comparison against the same test query.

Usage::

    from app.services.rag_debug_trace import get_tracer

    tracer = get_tracer()                 # no-op when disabled
    tracer.log_raw_query(query)
    tracer.log_query_embedding(...)
    ...

Every stage method is wrapped in try/except that logs the stage name and
the full exception before re-raising — "throws error" with no stage
attribution is not debuggable.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("rag.debug_trace")

# ---------------------------------------------------------------------------
# Sentinel for "enabled" check — avoids touching settings at import time.
# ---------------------------------------------------------------------------
_ENABLED: Optional[bool] = None


def _is_enabled() -> bool:
    global _ENABLED
    if _ENABLED is not None:
        return _ENABLED
    try:
        from app.core.config import settings

        _ENABLED = bool(getattr(settings, "rag_debug_trace", False))
    except Exception:
        _ENABLED = False
    return _ENABLED


def reset_enabled_cache() -> None:
    """Reset the cached enabled state (useful for tests)."""
    global _ENABLED
    _ENABLED = None


# ---------------------------------------------------------------------------
# Stage wrapper — never let a tracing failure pass silently
# ---------------------------------------------------------------------------

def _safe_log(stage: str, message: str, data: Any = None) -> None:
    """Log with stage attribution; if logging itself errors, log that too."""
    try:
        if data is not None:
            # Attempt JSON serialisation for structured data
            try:
                data_str = json.dumps(data, default=str, ensure_ascii=False)
            except (TypeError, ValueError):
                data_str = repr(data)
            logger.debug("[%s] %s\n%s", stage, message, data_str)
        else:
            logger.debug("[%s] %s", stage, message)
    except Exception as exc:
        logger.error("[%s] TRACE LOGGING FAILED: %s", stage, exc)


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

class RagDebugTracer:
    """Instruments all 9 stages of the retrieval→generation pipeline.

    Each method is a no-op when ``RAG_DEBUG_TRACE`` is not set.
    """

    # ---- Stage 1 ----
    def log_raw_query(self, query: str) -> None:
        """Stage 1 — the literal user string."""
        if not _is_enabled():
            return
        try:
            _safe_log("1_RAW_QUERY", "raw user query", {"query": query})
        except Exception as exc:
            logger.error("[1_RAW_QUERY] exception: %s", exc)
            raise

    # ---- Stage 2 ----
    def log_rewritten_query(self, rewritten: Optional[str]) -> None:
        """Stage 2 — rewritten query (or explicit 'disabled' marker)."""
        if not _is_enabled():
            return
        try:
            if rewritten is None:
                _safe_log("2_REWRITTEN_QUERY", "query rewriting: disabled")
            else:
                _safe_log(
                    "2_REWRITTEN_QUERY",
                    "rewritten query sent to embedding model",
                    {"rewritten_query": rewritten},
                )
        except Exception as exc:
            logger.error("[2_REWRITTEN_QUERY] exception: %s", exc)
            raise

    # ---- Stage 3 ----
    def log_query_embedding(
        self,
        model_name: str,
        model_version: str,
        dimension: int,
    ) -> None:
        """Stage 3 — embedding model + vector dimension.

        Always logged even when nothing looks wrong, because a silent
        dimension/model mismatch between index-time and query-time
        is a common cause of zero-result searches.
        """
        if not _is_enabled():
            return
        try:
            _safe_log(
                "3_QUERY_EMBEDDING",
                "embedding model and dimension used for query",
                {
                    "model_name": model_name,
                    "model_version": model_version,
                    "dimension": dimension,
                },
            )
        except Exception as exc:
            logger.error("[3_QUERY_EMBEDDING] exception: %s", exc)
            raise

    # ---- Stage 4 ----
    def log_lexical_retrieval(
        self,
        query: str,
        results: Sequence[Dict[str, Any]],
    ) -> None:
        """Stage 4 — top N lexical/BM25 candidates with scores."""
        if not _is_enabled():
            return
        try:
            compact = [
                {
                    "chunk_id": r.get("chunk_id") or r.get("document_id") or r.get("id"),
                    "score": r.get("score"),
                    "title": r.get("title"),
                }
                for r in (results or [])[:20]
            ]
            _safe_log(
                "4_LEXICAL_RETRIEVAL",
                f"lexical query={query!r}  candidates={len(results or [])}",
                {"query": query, "top_candidates": compact},
            )
        except Exception as exc:
            logger.error("[4_LEXICAL_RETRIEVAL] exception: %s", exc)
            raise

    # ---- Stage 5 ----
    def log_vector_retrieval(
        self,
        results: Sequence[Dict[str, Any]],
        *,
        pre_acl: bool = True,
    ) -> None:
        """Stage 5 — top N vector candidates with cosine scores, BEFORE ACL filter."""
        if not _is_enabled():
            return
        try:
            label = "BEFORE ACL filter" if pre_acl else "AFTER ACL filter"
            compact = [
                {
                    "chunk_id": r.get("chunk_id") or r.get("document_id") or r.get("id"),
                    "score": r.get("score"),
                    "title": r.get("title"),
                    "document_id": r.get("document_id"),
                }
                for r in (results or [])[:20]
            ]
            _safe_log(
                "5_VECTOR_RETRIEVAL",
                f"vector candidates {label}  count={len(results or [])}",
                {"label": label, "top_candidates": compact},
            )
        except Exception as exc:
            logger.error("[5_VECTOR_RETRIEVAL] exception: %s", exc)
            raise

    # ---- Stage 6 ----
    def log_acl_filter(
        self,
        must_clause: Any,
        pre_filter_count: int,
        post_filter_count: int,
    ) -> None:
        """Stage 6 — ACL/tenant filter clause and before/after counts.

        If pre_filter_count > 0 and post_filter_count == 0, this is a
        permissions bug, not a retrieval-quality bug.
        """
        if not _is_enabled():
            return
        try:
            is_permissions_bug = pre_filter_count > 0 and post_filter_count == 0
            msg = (
                f"pre_filter={pre_filter_count}  post_filter={post_filter_count}"
            )
            if is_permissions_bug:
                msg += (
                    "  *** PERMISSIONS BUG DETECTED *** "
                    "All candidates removed by ACL — do NOT touch chunking or embeddings"
                )
            _safe_log(
                "6_ACL_FILTER",
                msg,
                {
                    "must_clause": must_clause,
                    "pre_filter_count": pre_filter_count,
                    "post_filter_count": post_filter_count,
                    "is_permissions_bug": is_permissions_bug,
                },
            )
        except Exception as exc:
            logger.error("[6_ACL_FILTER] exception: %s", exc)
            raise

    # ---- Stage 7 ----
    def log_reranking(
        self,
        before: Optional[Sequence[Dict[str, Any]]] = None,
        after: Optional[Sequence[Dict[str, Any]]] = None,
        dropped: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> None:
        """Stage 7 — reranking scores before/after, or 'disabled'."""
        if not _is_enabled():
            return
        try:
            if before is None and after is None:
                _safe_log("7_RERANKING", "reranking: disabled")
                return
            _safe_log(
                "7_RERANKING",
                f"before={len(before or [])}  after={len(after or [])}  "
                f"dropped={len(dropped or [])}",
                {
                    "before": [
                        {"id": h.get("document_id"), "score": h.get("score") or h.get("boosted_score")}
                        for h in (before or [])[:20]
                    ],
                    "after": [
                        {"id": h.get("document_id"), "score": h.get("score") or h.get("boosted_score")}
                        for h in (after or [])[:20]
                    ],
                    "dropped": [
                        {"id": h.get("document_id"), "score": h.get("score") or h.get("boosted_score")}
                        for h in (dropped or [])[:20]
                    ],
                },
            )
        except Exception as exc:
            logger.error("[7_RERANKING] exception: %s", exc)
            raise

    # ---- Stage 8 ----
    def log_final_context(self, context_text: str, token_count: int) -> None:
        """Stage 8 — the literal text block handed to Qwen + token count.

        This is the single most useful line in the whole trace: if the
        relevant paragraph is in the source DOCX but not in this block,
        the failure is upstream of generation, full stop.
        """
        if not _is_enabled():
            return
        try:
            _safe_log(
                "8_FINAL_CONTEXT",
                f"context assembled  chars={len(context_text)}  tokens≈{token_count}",
                {"context_text": context_text, "token_count": token_count},
            )
        except Exception as exc:
            logger.error("[8_FINAL_CONTEXT] exception: %s", exc)
            raise

    # ---- Stage 9 ----
    def log_raw_response(self, response_text: str) -> None:
        """Stage 9 — Qwen's raw, unmodified response."""
        if not _is_enabled():
            return
        try:
            _safe_log(
                "9_RAW_RESPONSE",
                f"Qwen response  chars={len(response_text)}",
                {"response_text": response_text},
            )
        except Exception as exc:
            logger.error("[9_RAW_RESPONSE] exception: %s", exc)
            raise


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_TRACER: Optional[RagDebugTracer] = None


def get_tracer() -> RagDebugTracer:
    """Return the shared tracer instance (always safe — no-op when disabled)."""
    global _TRACER
    if _TRACER is None:
        _TRACER = RagDebugTracer()
    return _TRACER
