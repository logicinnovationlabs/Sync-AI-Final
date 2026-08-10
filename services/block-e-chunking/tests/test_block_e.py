"""Block E signoff E1-E4 — Phase-2 wrappers over verify scripts."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _run_verify_script(script_name: str) -> None:
    script = TESTS_DIR / script_name
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SERVICE_ROOT)
    # Windows consoles default to cp1252; force UTF-8 for verify script stdout.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(SERVICE_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_E1_chunk_integrity():
    """E1 — AST chunk integrity (verify_component4_code_chunker)."""
    _run_verify_script("verify_component4_code_chunker.py")


def test_E2_structural_throughput():
    """E2 — throughput harness structural pass (docs/min > 0)."""
    _run_verify_script("verify_component8_throughput_harness.py")


requires_e3_db = pytest.mark.skipif(
    not _port_open(5433),
    reason="Postgres on :5433 required for E3 re-embed trigger verification",
)


@requires_e3_db
def test_E3_reembed_triggered():
    """E3 — re-embed trigger on model version bump."""
    _run_verify_script("verify_component6_re_embed_trigger.py")


def test_E4_identical_chunk_ids_on_3_reprocess():
    """E4 — identical chunk ids across 3 reprocessing runs."""
    from verify_e4_idempotency import test_e4_idempotency

    assert test_e4_idempotency() is True
