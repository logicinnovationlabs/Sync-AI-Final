"""Performance measurement and regression helpers."""

from __future__ import annotations

from typing import Dict, List


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(len(ordered) * pct / 100)
    return ordered[min(index, len(ordered) - 1)]


def detect_regression(current_p95: float, baseline_p95: float, tolerance: float = 0.20) -> bool:
    """Return True if current p95 regresses beyond tolerance vs baseline."""
    if baseline_p95 <= 0:
        return False
    return current_p95 > baseline_p95 * (1.0 + tolerance)


def summarize(measurements: Dict[str, List[float]]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for label, values in measurements.items():
        out[label] = {
            "count": float(len(values)),
            "avg": (sum(values) / len(values)) if values else 0.0,
            "p95": percentile(values, 95),
            "p99": percentile(values, 99),
            "max": max(values) if values else 0.0,
        }
    return out
