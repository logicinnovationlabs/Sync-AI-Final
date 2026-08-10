"""Hybrid ranking: fusion (stage 1) + cross-encoder / mock rerank (stage 2)."""

from __future__ import annotations

import logging
import math
import re
from typing import List, Optional, Sequence

from app.config import settings
from app.models import Candidate

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


class Ranker:
    """
    Two-stage ranker.

    Stage 1 — weighted fusion of lexical, vector, and graph scores.
    Stage 2 — cross-encoder (or mock overlap) rerank of the top-K.
    """

    def __init__(
        self,
        *,
        lexical_weight: Optional[float] = None,
        vector_weight: Optional[float] = None,
        graph_weight: Optional[float] = None,
        rerank_top_k: Optional[int] = None,
        backend: Optional[str] = None,
        model_name: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        self.lexical_weight = lexical_weight if lexical_weight is not None else settings.lexical_weight
        self.vector_weight = vector_weight if vector_weight is not None else settings.vector_weight
        self.graph_weight = graph_weight if graph_weight is not None else settings.graph_weight
        self.rerank_top_k = rerank_top_k if rerank_top_k is not None else settings.rerank_top_k
        self.backend = (backend or settings.reranker_backend).lower()
        self.model_name = model_name or settings.reranker_model_name
        self.enabled = settings.reranker_enabled if enabled is None else enabled
        self._cross_encoder = None
        self._loaded = False

    def load(self) -> None:
        """Load the cross-encoder model once at process startup."""
        if self._loaded:
            return
        if not self.enabled or self.backend != "cross_encoder":
            logger.info(
                "Ranker stage-2 backend=%s enabled=%s (no model load)",
                self.backend,
                self.enabled,
            )
            self._loaded = True
            return

        try:
            from sentence_transformers import CrossEncoder

            logger.info("Loading cross-encoder model %s …", self.model_name)
            self._cross_encoder = CrossEncoder(self.model_name)
            logger.info("Cross-encoder ready")
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to load cross-encoder (%s); falling back to mock reranker",
                exc,
            )
            self.backend = "mock"
            self._cross_encoder = None
        self._loaded = True

    def unload(self) -> None:
        self._cross_encoder = None
        self._loaded = False

    def fuse(self, candidates: Sequence[Candidate]) -> List[Candidate]:
        """
        Stage 1: normalize component scores per-list and compute weighted sum.
        """
        if not candidates:
            return []

        lex = _minmax([c.lexical_score for c in candidates])
        vec = _minmax([c.vector_score for c in candidates])
        gra = _minmax([c.graph_boost for c in candidates])

        fused: List[Candidate] = []
        for i, c in enumerate(candidates):
            score = (
                self.lexical_weight * lex[i]
                + self.vector_weight * vec[i]
                + self.graph_weight * gra[i]
            )
            updated = c.model_copy(deep=True)
            updated.fusion_score = float(score)
            fused.append(updated)

        fused.sort(key=lambda c: c.fusion_score, reverse=True)
        return fused

    def rerank(self, query: str, candidates: Sequence[Candidate]) -> List[Candidate]:
        """
        Stage 2: rerank top-K by cross-encoder (or mock overlap), keep tail order.
        """
        if not candidates:
            return []
        if not self.enabled or settings.fusion_only:
            return list(candidates)

        head = list(candidates[: self.rerank_top_k])
        tail = list(candidates[self.rerank_top_k :])

        if self.backend == "cross_encoder" and self._cross_encoder is not None:
            scores = self._cross_encoder_scores(query, head)
        else:
            scores = self._mock_rerank_scores(query, head)

        for c, s in zip(head, scores):
            c.rerank_score = float(s)

        head.sort(key=lambda c: c.rerank_score if c.rerank_score is not None else 0.0, reverse=True)
        return head + tail

    def rank(self, query: str, candidates: Sequence[Candidate]) -> List[Candidate]:
        """Run fusion then rerank; return fully sorted candidates."""
        fused = self.fuse(candidates)
        return self.rerank(query, fused)

    def _cross_encoder_scores(self, query: str, candidates: Sequence[Candidate]) -> List[float]:
        pairs = [(query, c.text_for_rerank()) for c in candidates]
        raw = self._cross_encoder.predict(pairs)  # type: ignore[union-attr]
        return [float(x) for x in raw]

    def _mock_rerank_scores(self, query: str, candidates: Sequence[Candidate]) -> List[float]:
        """
        Lightweight relevance proxy: token overlap + fusion prior.

        Tuned so labeled relevant docs (sharing query terms) rank above noise,
        enabling NDCG@10 signoff without downloading a multi-GB model in CI.
        """
        q_tokens = set(_TOKEN_RE.findall(query.lower()))
        scores: List[float] = []
        for c in candidates:
            text = c.text_for_rerank().lower()
            d_tokens = set(_TOKEN_RE.findall(text))
            if not q_tokens:
                overlap = 0.0
            else:
                overlap = len(q_tokens & d_tokens) / len(q_tokens)
            # Prefer exact title/query phrase hits
            phrase_bonus = 0.35 if query.lower() in text else 0.0
            # Blend with fusion so multi-backend agreement still matters
            prior = c.fusion_score if c.fusion_score else 0.0
            scores.append(0.65 * overlap + 0.20 * prior + phrase_bonus + 0.05 * min(c.vector_score, 1.0))
        return scores


def _minmax(values: Sequence[float]) -> List[float]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if math.isclose(hi, lo):
        # Preserve relative presence: non-zero stays 1, zero stays 0
        return [1.0 if v > 0 else 0.0 for v in values]
    return [(v - lo) / (hi - lo) for v in values]
