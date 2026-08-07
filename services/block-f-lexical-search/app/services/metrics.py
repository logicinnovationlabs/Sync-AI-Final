"""In-process metrics for F1/F3 signoff and observability smoke checks."""

from __future__ import annotations

from typing import Any, Dict, List

_METRICS: Dict[str, Any] = {
    "query_latency_seconds": [],
    "index_lag_seconds": [],
    "facet_query_latency": [],
    "snippet_generation_latency": [],
    "auth_failure_rate": 0,
    "acl_filter_violation_attempts": 0,
    "indexing_throughput_docs": 0,
    "query_errors_total": 0,
}


def record_query_latency(seconds: float) -> None:
    samples: List[float] = _METRICS["query_latency_seconds"]
    samples.append(seconds)
    if len(samples) > 5000:
        _METRICS["query_latency_seconds"] = samples[-2500:]


def record_index_lag(seconds: float) -> None:
    samples: List[float] = _METRICS["index_lag_seconds"]
    samples.append(seconds)
    if len(samples) > 1000:
        _METRICS["index_lag_seconds"] = samples[-500:]


def record_acl_violation_attempt() -> None:
    _METRICS["acl_filter_violation_attempts"] += 1


def record_index_docs(n: int) -> None:
    _METRICS["indexing_throughput_docs"] += n


def snapshot() -> Dict[str, Any]:
    def _p95(samples: List[float]):
        if not samples:
            return None
        ordered = sorted(samples)
        idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
        return ordered[idx]

    ql = list(_METRICS["query_latency_seconds"])
    il = list(_METRICS["index_lag_seconds"])
    return {
        "query_latency": {
            "count": len(ql),
            "p50": sorted(ql)[len(ql) // 2] if ql else None,
            "p95": _p95(ql),
            "p99": sorted(ql)[min(len(ql) - 1, int(len(ql) * 0.99))] if ql else None,
        },
        "index_lag": {
            "count": len(il),
            "p95": _p95(il),
        },
        "acl_filter_violation_attempts": _METRICS["acl_filter_violation_attempts"],
        "indexing_throughput_docs": _METRICS["indexing_throughput_docs"],
        "query_errors_total": _METRICS["query_errors_total"],
    }
