"""
ACL compilation layer for Block C.

Computes and persists materialized ACLs with container inheritance and group expansion.
"""

from app.acl.compiler import ACLCompiler
from app.acl.container_service import ContainerService
from app.acl.filter import (
    DENY_PREFIX,
    deny_terms_for,
    document_is_visible,
    is_fail_closed,
    opensearch_acl_clause,
    qdrant_must_not_acl,
)

__all__ = [
    "ACLCompiler",
    "ContainerService",
    "DENY_PREFIX",
    "deny_terms_for",
    "document_is_visible",
    "is_fail_closed",
    "opensearch_acl_clause",
    "qdrant_must_not_acl",
]
