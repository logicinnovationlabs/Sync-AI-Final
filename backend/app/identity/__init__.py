"""
Identity resolution layer for Block C.

Resolves raw identity hints (emails, usernames) to stable principal_id values.
Tenant-scoped — never merges identities across tenants.
"""

from app.identity.resolver import IdentityResolver

__all__ = ["IdentityResolver"]
