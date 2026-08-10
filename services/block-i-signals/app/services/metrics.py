"""Lightweight in-process metrics for ingestion lag and query latency."""

from __future__ import annotations

import math
import threading
from typing import Any, Dict, List

_lock = threading.Lock()
_ingest_latencies: List[float] = []
_signal_latencies: Dict[str, List[float]] = {"user": [], "document": []}
_ingest_ok = 0
_ingest_dup = 0
_ingest_fail = 0


def _p95(samples: List[float]) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    idx = min(len(ordered) - 1, max(0, int(math.ceil(0.95 * len(ordered)) - 1)))
    return ordered[idx]


def record_ingest(ok: int, dup: int, fail: int) -> None:
    global _ingest_ok, _ingest_dup, _ingest_fail
    with _lock:
        _ingest_ok += ok
        _ingest_dup += dup
        _ingest_fail += fail


def record_ingest_latency(seconds: float) -> None:
    with _lock:
        _ingest_latencies.append(seconds)
        if len(_ingest_latencies) > 5000:
            del _ingest_latencies[:-2500]


def record_signal_query_latency(kind: str, seconds: float) -> None:
    with _lock:
        bucket = _signal_latencies.setdefault(kind, [])
        bucket.append(seconds)
        if len(bucket) > 5000:
            del bucket[:-2500]


def snapshot() -> Dict[str, Any]:
    with _lock:
        return {
            "ingest_ok": _ingest_ok,
            "ingest_dup": _ingest_dup,
            "ingest_fail": _ingest_fail,
            "ingest_latency_p95_ms": (
                None if _p95(_ingest_latencies) is None else round(_p95(_ingest_latencies) * 1000, 3)
            ),
            "signal_user_latency_p95_ms": (
                None
                if _p95(_signal_latencies.get("user", [])) is None
                else round(_p95(_signal_latencies["user"]) * 1000, 3)
            ),
            "signal_document_latency_p95_ms": (
                None
                if _p95(_signal_latencies.get("document", [])) is None
                else round(_p95(_signal_latencies["document"]) * 1000, 3)
            ),
        }


def reset_metrics() -> None:
    global _ingest_ok, _ingest_dup, _ingest_fail
    with _lock:
        _ingest_ok = _ingest_dup = _ingest_fail = 0
        _ingest_latencies.clear()
        for k in _signal_latencies:
            _signal_latencies[k].clear()
