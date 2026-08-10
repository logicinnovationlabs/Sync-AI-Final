"""Block C deep signoff (C1-C4+) — wraps backend normalization/ACL signoff suite."""

from __future__ import annotations

from tests.test_signoff_block_c import (  # noqa: F401
    test_c1_determinism_identical_output as test_C1_determinism,
    test_c2_acl_fidelity as test_C2_acl_fidelity,
    test_c3_revocation_propagation as test_C3_revocation_propagation,
    test_c4_identity_resolution_accuracy as test_C4_identity_resolution_accuracy,
)

__all__ = [
    "test_C1_determinism",
    "test_C2_acl_fidelity",
    "test_C3_revocation_propagation",
    "test_C4_identity_resolution_accuracy",
]