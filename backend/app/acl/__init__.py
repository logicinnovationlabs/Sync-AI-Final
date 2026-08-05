"""
ACL compilation layer for Block C.

Computes and persists materialized ACLs with container inheritance and group expansion.
"""

from app.acl.compiler import ACLCompiler
from app.acl.container_service import ContainerService

__all__ = ["ACLCompiler", "ContainerService"]
