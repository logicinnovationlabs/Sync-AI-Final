"""Block D signoff D1-D4 — Phase-2 wrappers over local criterion tests."""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


requires_postgres = pytest.mark.skipif(
    not _port_open(5435),
    reason="Local Postgres on :5435 required for Block D Phase-2 tests",
)


def _run_pytest_node(node_id: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", node_id, "-q"],
        cwd=str(SERVICE_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@requires_postgres
def test_D1_provisioning_time():
    """D1 — provision 10 fresh tenants in under 5 minutes."""
    _run_pytest_node(
        "tests/test_D1_provisioning_time_local.py::TestD1ProvisioningTimeLocal::test_D1_provisioning_time_local"
    )


@requires_postgres
def test_D2_backup_restore_counts_match():
    """D2 — backup/restore row and object counts match exactly."""
    _run_pytest_node(
        "tests/test_D2_backup_restore_local.py::TestD2BackupRestoreLocal::test_D2_backup_restore_integrity_local"
    )


@requires_postgres
def test_D3_tenant_isolation_disjoint():
    """D3 — cross-tenant reads blocked at storage layer."""
    _run_pytest_node(
        "tests/test_D3_storage_isolation_local.py::TestD3StorageIsolationLocal::test_D3_schema_permission_isolation"
    )


@requires_postgres
def test_D4_key_rotation_increments_version():
    """D4 — key rotation under load with zero data loss."""
    _run_pytest_node(
        "tests/test_D4_key_rotation_local.py::TestD4KeyRotationLocal::test_D4_key_rotation_with_load"
    )
