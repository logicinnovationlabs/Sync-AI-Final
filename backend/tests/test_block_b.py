"""Block B deep signoff (B1-B5+) — wraps backend connector signoff suite."""

from __future__ import annotations

from tests.test_signoff_block_b import (  # noqa: F401
    test_B1_backfill_completeness,
    test_B2_webhook_incremental_correctness,
    test_B3_webhook_authenticity_rejection,
    test_B4_rate_limit_resilience,
    test_B5_credential_leakage,
    test_b5_checkpoint_resume,
)

__all__ = [
    "test_B1_backfill_completeness",
    "test_B2_webhook_incremental_correctness",
    "test_B3_webhook_authenticity_rejection",
    "test_B4_rate_limit_resilience",
    "test_B5_credential_leakage",
    "test_b5_checkpoint_resume",
]
