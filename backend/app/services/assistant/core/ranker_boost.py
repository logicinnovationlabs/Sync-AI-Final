"""Activity-signal boost applied on top of Ranking Service (Federator) scores."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


@dataclass
class RankedHit:
    document_id: str
    base_score: float
    boosted_score: float
    title: str = ""
    snippet: str = ""
    sources: List[str] = field(default_factory=list)
    boost_reason: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_base_hits(federator_payload: Mapping[str, Any]) -> List[RankedHit]:
    """
    Map Federator / Ranking Service results into RankedHit objects.

    base_score is taken from the Federator `score` field and is preserved
    unmodified; boost is applied only onto boosted_score.
    """
    results = federator_payload.get("results") or federator_payload.get("hits") or []
    hits: List[RankedHit] = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        doc_id = str(item.get("document_id") or item.get("id") or "")
        if not doc_id:
            continue
        base = _as_float(item.get("score"), 0.0)
        hits.append(
            RankedHit(
                document_id=doc_id,
                base_score=base,
                boosted_score=base,
                title=str(item.get("title") or ""),
                snippet=str(item.get("snippet") or item.get("body") or ""),
                sources=list(item.get("sources") or []),
                meta=dict(item),
            )
        )
    return hits


def _recent_doc_weights(signals_payload: Mapping[str, Any]) -> Dict[str, float]:
    """
    Build document_id -> boost weight from Block I user signals.

    Supports several shapes produced by Block I / fixtures:
      - signals.top_viewed_docs: [{document_id, score|views|recency}]
      - top_viewed_docs at top level
      - recent_views: [{document_id, event_time}]
    """
    weights: Dict[str, float] = {}
    signals = signals_payload.get("signals") if isinstance(signals_payload.get("signals"), Mapping) else signals_payload

    def ingest(entries: Iterable[Any], default_weight: float) -> None:
        for entry in entries:
            if isinstance(entry, str):
                weights[entry] = max(weights.get(entry, 0.0), default_weight)
                continue
            if not isinstance(entry, Mapping):
                continue
            doc_id = str(entry.get("document_id") or entry.get("object_id") or entry.get("id") or "")
            if not doc_id:
                continue
            w = _as_float(
                entry.get("score", entry.get("views", entry.get("weight", default_weight))),
                default_weight,
            )
            # Temporal boost: fresher events get a mild extra bump.
            event_time = entry.get("event_time") or entry.get("last_viewed_at")
            if event_time:
                try:
                    ts = datetime.fromisoformat(str(event_time).replace("Z", "+00:00"))
                    age_h = max(
                        0.0,
                        (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
                        / 3600.0,
                    )
                    w += max(0.0, 0.15 * (1.0 - min(age_h, 168.0) / 168.0))
                except ValueError:
                    pass
            weights[doc_id] = max(weights.get(doc_id, 0.0), w)

    if isinstance(signals, Mapping):
        ingest(signals.get("top_viewed_docs") or [], 0.25)
        ingest(signals.get("authored_docs") or [], 0.20)
        ingest(signals.get("recent_views") or [], 0.30)
        ingest(signals.get("worked_on_docs") or [], 0.22)
    ingest(signals_payload.get("top_viewed_docs") or [], 0.25)
    ingest(signals_payload.get("recent_views") or [], 0.30)
    return weights


def apply_signal_boost(
    base_hits: Sequence[RankedHit],
    signals_payload: Optional[Mapping[str, Any]],
    *,
    boost_scale: float = 0.35,
) -> List[RankedHit]:
    """
    Apply Activity Signal boost on top of Ranking Service output.

    - base_score is never mutated.
    - boosted_score = base_score + boost_scale * signal_weight (additive).
    - Ordering is by boosted_score descending.
    """
    weights = _recent_doc_weights(signals_payload or {})
    boosted: List[RankedHit] = []
    for hit in base_hits:
        w = weights.get(hit.document_id, 0.0)
        delta = boost_scale * w
        boosted.append(
            RankedHit(
                document_id=hit.document_id,
                base_score=hit.base_score,
                boosted_score=hit.base_score + delta,
                title=hit.title,
                snippet=hit.snippet,
                sources=list(hit.sources),
                boost_reason=f"activity_signal+{delta:.4f}" if delta else None,
                meta=dict(hit.meta),
            )
        )
    boosted.sort(key=lambda h: h.boosted_score, reverse=True)
    return boosted


def max_confidence(hits: Sequence[RankedHit]) -> float:
    if not hits:
        return 0.0
    return max(h.boosted_score for h in hits)


def retrieval_confidence(hits: Sequence[RankedHit]) -> float:
    """Map retrieval scores onto a 0–1 confidence used for search-vs-read.

    Federator fusion uses RRF with k=60, so rank-1 is ~1/61 ≈ 0.016. That is
    *not* cosine similarity. Treating it as 0–1 made every query fall below
    CONFIDENCE_THRESHOLD (0.6) and deep-read a weakly related top document.
    """
    if not hits:
        return 0.0
    top = hits[0]
    meta = top.meta if isinstance(top.meta, dict) else {}
    nested = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}

    def _pick(*keys: str) -> float:
        for src in (meta, nested, top.meta):
            if not isinstance(src, dict):
                continue
            for key in keys:
                val = _as_float(src.get(key), default=-1.0)
                if val >= 0.0:
                    return val
        return -1.0

    vector = _pick("vector_score")
    lexical = _pick("lexical_score")
    similarity = max(vector, lexical)
    if similarity >= 0.05:
        return min(1.0, similarity)

    rrf = max(top.boosted_score, top.base_score, _pick("fusion_score", "score"))
    if rrf <= 0.0:
        return 0.0
    if rrf <= 0.05:
        # Rank-1 single-list RRF ≈ 1/61. Normalize so top-of-list is ~1.0.
        return min(1.0, rrf * 61.0)
    return min(1.0, rrf)
