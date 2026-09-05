"""Role → JWT scope mapping for Block N admin-first RBAC."""

from __future__ import annotations

from typing import List

ADMIN_SCOPES: List[str] = [
    "search.read",
    "document.read",
    "connectors.read",
    "connectors.write",
    "admin.audit.read",
    "admin.users.read",
    "admin.users.write",
    "admin.connectors.read",
    "admin.connectors.write",
    "admin.sessions.revoke",
    "graph.admin",
    "signals.admin",
]

MEMBER_SCOPES: List[str] = [
    "search.read",
    "document.read",
    "connectors.read",
    "connectors.write",
]

VIEWER_SCOPES: List[str] = [
    "search.read",
    "document.read",
    "connectors.read",
]


def scopes_for_role(role: str) -> List[str]:
    """Return the JWT scope list for a persisted user role."""
    if role == "owner":
        return list(ADMIN_SCOPES)
    if role == "admin":
        return list(ADMIN_SCOPES)
    if role == "viewer":
        return list(VIEWER_SCOPES)
    return list(MEMBER_SCOPES)
