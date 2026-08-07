"""Unit tests for fusion + reranking."""

from __future__ import annotations

from app.models import Candidate
from app.services.ranker import Ranker


def test_fusion_prefers_multi_signal_agreement():
    ranker = Ranker(lexical_weight=0.4, vector_weight=0.4, graph_weight=0.2, backend="mock")
    candidates = [
        Candidate(document_id="a", lexical_score=10, vector_score=0.1, graph_boost=0.0, title="a"),
        Candidate(document_id="b", lexical_score=5, vector_score=0.9, graph_boost=0.8, title="b"),
        Candidate(document_id="c", lexical_score=1, vector_score=0.2, graph_boost=0.1, title="c"),
    ]
    fused = ranker.fuse(candidates)
    assert fused[0].document_id == "b"
    assert fused[0].fusion_score >= fused[1].fusion_score


def test_rerank_boosts_query_overlap():
    ranker = Ranker(backend="mock", enabled=True, rerank_top_k=10)
    ranker.load()
    candidates = [
        Candidate(
            document_id="noise",
            title="unrelated payroll spreadsheet",
            snippet="numbers and salaries",
            lexical_score=9.0,
            fusion_score=0.9,
        ),
        Candidate(
            document_id="hit",
            title="kubernetes guide",
            snippet="How does kubernetes work? cluster scheduling",
            lexical_score=3.0,
            fusion_score=0.4,
        ),
    ]
    # Fusion would prefer noise; rerank should elevate the topical hit
    fused = ranker.fuse(candidates)
    ranked = ranker.rerank("How does kubernetes work?", fused)
    assert ranked[0].document_id == "hit"
    assert ranked[0].rerank_score is not None


def test_rank_empty():
    ranker = Ranker(backend="mock")
    assert ranker.rank("q", []) == []


def test_fusion_only_skips_rerank(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "fusion_only", True)
    ranker = Ranker(backend="mock", enabled=True)
    cands = [
        Candidate(document_id="a", lexical_score=1, title="alpha"),
        Candidate(document_id="b", lexical_score=2, title="beta"),
    ]
    ranked = ranker.rank("alpha", cands)
    assert all(c.rerank_score is None for c in ranked)
