"""Block A deep signoff (A1-A5) — closeout suite against real Postgres/Redis.

Prefer: USE_REAL_SERVICES=1 with block-a-verify-pg :5434.
Provisional HTTP mock criteria live in tests/test_block_a.py at repo root.
"""

from __future__ import annotations

# Re-export closeout criterion tests under architecture IDs
from tests.test_signoff_closeout_local import (  # noqa: F401
    test_A1_tenant_binding_integrity_closeout as test_A1_tenant_binding_integrity,
    test_A2_revocation_latency_closeout as test_A2_revocation_latency,
    test_A3_scim_idempotency_process_restart_closeout as test_A3_scim_idempotency,
    test_A4_cross_tenant_replay_rejection_closeout as test_A4_cross_tenant_replay_rejection,
    test_A5_scope_enforcement_closeout as test_A5_scope_enforcement,
)

__all__ = [
    "test_A1_tenant_binding_integrity",
    "test_A2_revocation_latency",
    "test_A3_scim_idempotency",
    "test_A4_cross_tenant_replay_rejection",
    "test_A5_scope_enforcement",
]