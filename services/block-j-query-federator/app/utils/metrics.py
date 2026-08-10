"""Lightweight in-process metrics (Prometheus-compatible text optional)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict, List


class MetricsRegistry:
    """Simple counters / latency histograms for observability."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: Dict[str, float] = defaultdict(float)
        self.latencies: Dict[str, List[float]] = defaultdict(list)

    def incr(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = _label_key(name, labels)
        with self._lock:
            self.counters[key] += value

    def observe(self, name: str, value_ms: float, **labels: str) -> None:
        key = _label_key(name, labels)
        with self._lock:
            bucket = self.latencies[key]
            bucket.append(value_ms)
            # Cap retained samples
            if len(bucket) > 5000:
                del bucket[: len(bucket) - 2500]

    def timed(self, name: str, **labels: str):
        """Context manager that records elapsed ms."""
        registry = self

        class _Timer:
            def __enter__(self_inner):
                self_inner._start = time.perf_counter()
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                elapsed = (time.perf_counter() - self_inner._start) * 1000.0
                registry.observe(name, elapsed, **labels)
                return False

        return _Timer()

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "counters": dict(self.counters),
                "latencies": {
                    k: {
                        "count": len(v),
                        "p50": _percentile(v, 50),
                        "p95": _percentile(v, 95),
                        "max": max(v) if v else 0.0,
                    }
                    for k, v in self.latencies.items()
                },
            }

    def prometheus_text(self) -> str:
        """Render a minimal Prometheus exposition format."""
        lines: List[str] = []
        snap = self.snapshot()
        for key, value in snap["counters"].items():  # type: ignore[union-attr]
            lines.append(f"# TYPE {key.split('{')[0]} counter")
            lines.append(f"{key} {value}")
        for key, stats in snap["latencies"].items():  # type: ignore[union-attr]
            base = key.split("{")[0]
            lines.append(f"# TYPE {base}_ms summary")
            suffix = key[len(base) :] if "{" in key else ""
            lines.append(f"{base}_ms{{quantile=\"0.5\"{suffix[1:] if suffix else ''}}} {stats['p50']}")
            # Keep labels simple: emit count/max without complex label rewrite
            lines.append(f"{base}_count{suffix} {stats['count']}")
            lines.append(f"{base}_max_ms{suffix} {stats['max']}")
        return "\n".join(lines) + "\n"


def _label_key(name: str, labels: Dict[str, str]) -> str:
    if not labels:
        return name
    parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{parts}}}"


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


metrics = MetricsRegistry()
