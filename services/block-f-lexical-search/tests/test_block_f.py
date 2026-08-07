"""Block F signoff F1-F4 — wraps existing criterion tests."""

from .test_latency import test_F1_query_latency_p95
from .test_acl_redteam import test_F2_acl_redteam_zero_unauthorized as test_F2_acl_zero_leaks
from .test_index_lag import test_F3_index_lag_p95 as test_F3_index_lag
from .test_facet_accuracy import test_F4_facet_accuracy

__all__ = [
    "test_F1_query_latency_p95",
    "test_F2_acl_zero_leaks",
    "test_F3_index_lag",
    "test_F4_facet_accuracy",
]