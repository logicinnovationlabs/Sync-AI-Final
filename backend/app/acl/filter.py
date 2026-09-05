"""Single search-time ACL filter (deny-override).

Index-time compilation lives in ``app.acl.compiler``. Every search backend
(F lexical, G vector, J federated, L assistant) must apply this module so an
explicit deny cannot leak through a ``MatchAny``/terms allow-list.

Term conventions (stored on the document/chunk):
  ``user:alice`` / ``group:eng``  — allow
  ``deny:user:bob``               — explicit deny of that principal/group

Fail-closed: empty caller ACL → no documents.
``*`` is a test/ops bypass (used by Block G recall harnesses).

Admin access overrides (Part 2.3):
Admin-set allow/deny overrides are checked BEFORE the existing ACL logic.
- Deny override → exclude regardless of underlying ACL
- Allow override → include (tenant boundary validated at set time)
- No override → fall through to existing ACL compile logic
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Mapping, Set
from uuid import UUID

DENY_PREFIX = "deny:"


def is_fail_closed(user_acl: Sequence[str]) -> bool:
    return not any(t for t in user_acl if t)


def is_bypass(user_acl: Sequence[str]) -> bool:
    return "*" in user_acl


def deny_terms_for(user_acl: Sequence[str]) -> List[str]:
    return [f"{DENY_PREFIX}{term}" for term in user_acl if term and term != "*"]


def document_is_visible(
    user_acl: Sequence[str],
    doc_acl: Optional[Iterable[str]],
) -> bool:
    """Return True iff ``user_acl`` may see a document with ``doc_acl`` terms."""
    if is_fail_closed(user_acl):
        return False
    if is_bypass(user_acl):
        return True

    terms = [t for t in (doc_acl or []) if t]
    # Empty document ACL is private, not tenant-public.
    if not terms:
        return False

    deny_full = set(deny_terms_for(user_acl))
    if any(t in deny_full for t in terms):
        return False

    positive = [t for t in terms if not t.startswith(DENY_PREFIX)]
    if not positive:
        return False
    allow = set(user_acl)
    return any(t in allow for t in positive)


def opensearch_acl_clause(
    user_acl: Sequence[str],
    field: str = "acl_filter_terms",
) -> Optional[Dict[str, Any]]:
    """Bool filter clause for OpenSearch, or None to skip (bypass)."""
    if is_fail_closed(user_acl):
        raise ValueError("empty ACL is fail-closed; do not query")
    if is_bypass(user_acl):
        return None

    deny = deny_terms_for(user_acl)
    return {
        "bool": {
            "must": [{"terms": {field: list(user_acl)}}],
            "must_not": [{"terms": {field: deny}}] if deny else [],
        }
    }


def qdrant_must_not_acl(qm: Any, user_acl: Sequence[str], field: str = "acl_terms"):
    """Qdrant FieldCondition for explicit deny, or None."""
    deny = deny_terms_for(user_acl)
    if not deny:
        return None
    return qm.FieldCondition(key=field, match=qm.MatchAny(any=deny))


def acl_terms_from_jwt(payload: Mapping[str, Any]) -> List[str]:
    """Build caller ACL from JWT claims only. Never from a request body.

    ``*`` is stripped even if present on the token — HTTP search must not
    honor the test/ops bypass. Store-level signoff harnesses still pass
    ``acl_terms`` directly into OpenSearch/Qdrant.
    """
    terms: List[str] = []
    seen: set[str] = set()

    def _add(raw: Any) -> None:
        value = str(raw).strip() if raw is not None else ""
        if not value or value == "*" or value in seen:
            return
        seen.add(value)
        terms.append(value)

    claimed = payload.get("acl_terms") or payload.get("acl_filter_terms") or []
    if isinstance(claimed, (list, tuple)):
        for item in claimed:
            _add(item)

    principal = payload.get("sub") or payload.get("principal_id") or payload.get("user_id")
    if principal:
        _add(principal)
        _add(f"user:{principal}")

    email = payload.get("email")
    if email:
        _add(str(email).strip().lower())
        _add(f"user:{str(email).strip().lower()}")

    groups = payload.get("groups") or []
    if isinstance(groups, (list, tuple)):
        for group in groups:
            _add(group)
            group_str = str(group)
            if group_str and not group_str.startswith("group:"):
                _add(f"group:{group_str}")

    return terms


def document_is_visible_with_admin_override(
    user_acl: Sequence[str],
    doc_acl: Optional[Iterable[str]],
    admin_denied_ids: Optional[Set[str]] = None,
    document_id: Optional[str] = None,
) -> bool:
    """
    Return True iff ``user_acl`` may see a document with ``doc_acl`` terms,
    checking admin access overrides BEFORE the existing ACL logic.
    
    Enforcement order (per Part 2.3 requirements):
    1. Check admin_access_overrides for this (document, user) pair first
    2. If deny → exclude regardless of what the underlying ACL says
    3. If allow → include (tenant boundary validated at set time)
    4. If no override → fall through to existing ACL compile logic unchanged
    
    Handles dual-indexing by normalizing document IDs (stripping source_type
    prefixes) before comparison, ensuring a deny on one ID variant blocks all
    variants of the same document.
    
    Args:
        user_acl: User's ACL terms from JWT
        doc_acl: Document's ACL terms
        admin_denied_ids: Set of document IDs with deny overrides for this user
        document_id: Document ID to check against admin_denied_ids
        
    Returns:
        True if document is visible, False otherwise
    """
    if admin_deny_blocks_document(document_id, admin_denied_ids):
        return False
    return document_is_visible(user_acl, doc_acl)


def _normalize_document_id(doc_id: Optional[str]) -> Optional[str]:
    """
    Normalize document ID by stripping source_type prefix if present.
    
    This handles dual-indexing where the same document may be stored with
    both prefixed (e.g., "google_gmail_19c695373f33fcec") and unprefixed
    (e.g., "19c695373f33fcec") IDs. Normalization ensures deny overrides
    work regardless of which variant is stored or queried.
    
    Args:
        doc_id: Document ID that may have a source_type prefix
        
    Returns:
        Normalized document ID without prefix, or None if input is None or empty
    """
    if not doc_id or doc_id == "":
        return None
    
    # Common source_type prefixes to strip
    prefixes = [
        "google_gmail_",
        "google_drive_",
        "slack_",
        "notion_",
        "confluence_",
        "dropbox_",
        "onedrive_",
        "sharepoint_",
    ]
    
    normalized = str(doc_id)
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    
    return normalized


def admin_deny_blocks_document(
    document_id: Optional[str],
    admin_denied_ids: Optional[Set[str]],
) -> bool:
    """True if an admin deny override covers this document id or a dual-index alias."""
    if not document_id or not admin_denied_ids:
        return False
    normalized_denied = {_normalize_document_id(did) for did in admin_denied_ids}
    normalized_denied.discard(None)
    candidates = {str(document_id)}
    prefixes = ("google_gmail_", "google_drive_", "sharepoint_")
    raw = str(document_id)
    for prefix in prefixes:
        if raw.startswith(prefix) and raw[len(prefix) :]:
            candidates.add(raw[len(prefix) :])
        elif not raw.startswith(prefix):
            candidates.add(f"{prefix}{raw}")
    for candidate in candidates:
        if candidate in admin_denied_ids:
            return True
        if _normalize_document_id(candidate) in normalized_denied:
            return True
    return False


def filter_results_with_admin_overrides(
    results: List[Any],
    admin_denied_ids: Set[str],
    document_id_field: str = "document_id",
) -> List[Any]:
    """
    Filter search results to remove documents with admin deny overrides.
    
    This is applied after search retrieval to enforce admin overrides
    at query time without modifying the existing ACL compile pipeline.
    
    Handles dual-indexing by normalizing document IDs (stripping source_type
    prefixes) before comparison, ensuring a deny on one ID variant blocks all
    variants of the same document.
    
    Args:
        results: List of search result dictionaries or Pydantic objects
        admin_denied_ids: Set of document IDs with deny overrides
        document_id_field: Field name containing document ID in results
        
    Returns:
        Filtered list of results excluding denied documents
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not admin_denied_ids:
        logger.info("No admin_denied_ids provided, returning all results")
        return results
    
    # Normalize denied IDs to handle dual-indexing variants
    normalized_denied_ids = {_normalize_document_id(did) for did in admin_denied_ids}
    normalized_denied_ids.discard(None)  # Remove any None values
    
    logger.info(f"Filtering {len(results)} results, denied_ids: {admin_denied_ids}")
    logger.info(f"Normalized denied_ids: {normalized_denied_ids}")
    
    # Handle both dict and Pydantic objects
    def get_document_id(result):
        if hasattr(result, 'get'):
            # It's a dict-like object
            return result.get(document_id_field)
        else:
            # It's a Pydantic object or similar
            return getattr(result, document_id_field, None)
    
    # Log document IDs in results
    result_ids = [get_document_id(result) for result in results]
    logger.info(f"Result document IDs: {result_ids[:10]}")  # First 10
    
    filtered = [
        result
        for result in results
        if not admin_deny_blocks_document(get_document_id(result), admin_denied_ids)
    ]
    
    logger.info(f"Filtered to {len(filtered)} results")
    
    return filtered
