"""Unified ACL term generation for indexing and querying.

This module provides a single source of truth for generating ACL terms from
user identities. MUST match the logic in `acl.filter.acl_terms_from_jwt` to
ensure indexed documents can be retrieved by their owners.

Usage:
    # During indexing:
    from app.acl.term_generator import generate_acl_terms_for_user
    acl_terms = generate_acl_terms_for_user(
        principal_id="550e8400-e29b-41d4-a716-446655440000",
        email="john@company.com",
        groups=["engineering", "admin"]
    )

    # During querying:
    from app.acl.filter import acl_terms_from_jwt
    acl_terms = acl_terms_from_jwt(jwt_payload)
"""

from typing import List, Optional, Sequence


def generate_acl_terms_for_user(
    principal_id: Optional[str] = None,
    email: Optional[str] = None,
    groups: Optional[Sequence[str]] = None,
) -> List[str]:
    """
    Generate ACL terms for a user identity in all required formats.

    This function MUST generate terms that exactly match what `acl_terms_from_jwt`
    extracts from a JWT payload. Any mismatch will cause indexed documents to
    be invisible during search.

    Args:
        principal_id: User's principal ID (UUID or other unique identifier)
        email: User's email address (will be normalized to lowercase)
        groups: List of group identifiers the user belongs to

    Returns:
        List of ACL terms in all required formats:
        - principal_id (bare)
        - user:principal_id (prefixed)
        - email (bare, lowercase)
        - user:email (prefixed, lowercase)
        - group (bare)
        - group:group (prefixed if not already)

    Examples:
        >>> generate_acl_terms_for_user(
        ...     principal_id="user-123",
        ...     email="Alice@Company.COM",
        ...     groups=["eng"]
        ... )
        ['user-123', 'user:user-123', 'alice@company.com', 'user:alice@company.com', 'eng', 'group:eng']
    """
    terms: List[str] = []
    seen: set = set()

    def _add(value: str) -> None:
        """Add a term if not already present (deduplication)."""
        value = value.strip()
        if value and value not in seen and value != "*":
            seen.add(value)
            terms.append(value)

    # Add principal_id in both formats
    if principal_id:
        principal = str(principal_id).strip()
        if principal:
            _add(principal)
            if not principal.startswith(("user:", "group:")):
                _add(f"user:{principal}")

    # Add email in both formats (normalized to lowercase)
    if email:
        email_normalized = str(email).strip().lower()
        if email_normalized:
            _add(email_normalized)
            _add(f"user:{email_normalized}")

    # Add groups in both formats
    if groups:
        for group in groups:
            group_str = str(group).strip()
            if group_str:
                _add(group_str)
                if not group_str.startswith("group:"):
                    _add(f"group:{group_str}")

    return terms


def merge_acl_terms(*term_lists: Sequence[str]) -> List[str]:
    """
    Merge multiple ACL term lists, removing duplicates while preserving order.

    Args:
        *term_lists: Variable number of ACL term lists to merge

    Returns:
        Deduplicated list of ACL terms

    Example:
        >>> merge_acl_terms(
        ...     ["user-123", "user:user-123"],
        ...     ["alice@company.com", "user:user-123"]
        ... )
        ['user-123', 'user:user-123', 'alice@company.com']
    """
    merged: List[str] = []
    seen: set = set()

    for term_list in term_lists:
        for term in term_list or []:
            term_str = str(term).strip()
            if term_str and term_str not in seen and term_str != "*":
                seen.add(term_str)
                merged.append(term_str)

    return merged
