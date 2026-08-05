"""
Re-exports from core/models.py for import convenience.
"""

from app.core.models import (
    Principal,
    Group,
    IdentityHint,
    ResolvedIdentity,
)

__all__ = ["Principal", "Group", "IdentityHint", "ResolvedIdentity"]
