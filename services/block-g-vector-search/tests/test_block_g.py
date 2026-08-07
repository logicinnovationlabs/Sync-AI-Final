"""Block G signoff G1-G4 — wraps existing criterion tests."""

from .test_recall import test_G1_recall_at_10 as test_G1_recall_at_10_ge_085
from .test_acl_prefilter import test_G2_acl_prefilter_zero_leak as test_G2_acl_zero_leaks
from .test_latency import test_G3_latency_p95 as test_G3_p95_le_150ms
from .test_model_versions import test_G4_model_version_filter as test_G4_model_version_handling

__all__ = [
    "test_G1_recall_at_10_ge_085",
    "test_G2_acl_zero_leaks",
    "test_G3_p95_le_150ms",
    "test_G4_model_version_handling",
]