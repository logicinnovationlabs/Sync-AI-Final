"""Shared helpers for architecture section 24 signoff tests (Blocks Z, A-H, J)."""

from __future__ import annotations

import os
from typing import Iterable, Sequence

import pytest

from tests.conftest import TestConfig


def using_real_services() -> bool:
    return TestConfig.using_real()


def using_mocks() -> bool:
    return TestConfig.using_mocks()


require_mocks = pytest.mark.skipif(
    using_real_services(),
    reason="Phase 1 provisional criterion requires mocks (unset USE_REAL_SERVICES)",
)

require_real = pytest.mark.skipif(
    not using_real_services(),
    reason="Phase 2 integration requires USE_REAL_SERVICES=1 (or TEST_PHASE=integration)",
)


def percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * pct / 100.0))
    return float(ordered[idx])


def p95(values: Sequence[float]) -> float:
    return percentile(values, 95)


def assert_pass(criterion_id: str, condition: bool, detail: str = "") -> None:
    msg = f"{criterion_id} FAIL"
    if detail:
        msg = f"{msg}: {detail}"
    assert condition, msg
    print(f"{criterion_id} PASS" + (f": {detail}" if detail else ""))


def env_present(name: str) -> bool:
    val = os.environ.get(name)
    return bool(val and str(val).strip())


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def skip_unless_ports(ports: Iterable[int], host: str = "127.0.0.1") -> None:
    missing = [p for p in ports if not tcp_open(host, p)]
    if missing:
        pytest.skip(f"Required ports not open on {host}: {missing}")