"""ACL prefilter helpers for vector queries."""

from typing import Any, Dict, List, Optional, Set


def normalize_acl_terms(terms: Optional[List[str]]) -> List[str]:
    """Deduplicate and strip empty ACL terms."""
    if not terms:
        return []
    seen: Set[str] = set()
    out: List[str] = []
    for term in terms:
        if not term:
            continue
        cleaned = str(term).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def acl_allows(chunk_acl_terms: List[str], user_acl_terms: List[str]) -> bool:
    """
    True if the user may read the chunk.

    Rule: non-empty intersection of principal/group IDs.
    Empty chunk ACL means no access (fail-closed).
    Explicit deny: terms on the chunk override allow (Block F parity).
    """
    if not chunk_acl_terms or not user_acl_terms:
        return False
    denies = {t[5:] for t in chunk_acl_terms if t.startswith("deny:")}
    allows = {t for t in chunk_acl_terms if not t.startswith("deny:")}
    user = set(user_acl_terms)
    if denies & user:
        return False
    return bool(allows & user)


def build_qdrant_acl_conditions(user_acl_terms: List[str]) -> List[Dict[str, Any]]:
    """
    Build Qdrant-compatible condition descriptors for ACL overlap + deny override.

    Used by qdrant_store to construct FieldCondition MatchAny filters and
    must_not MatchAny on deny:<caller-term> (mirrors Block F OpenSearch filter).
    """
    terms = normalize_acl_terms(user_acl_terms)
    if not terms:
        return []
    return [
        {"key": "acl_terms", "match_any": terms},
        {"key": "acl_terms", "must_not_match_any": [f"deny:{t}" for t in terms]},
    ]


def filter_results_by_acl(
    results: List[Dict[str, Any]],
    user_acl_terms: List[str],
) -> List[Dict[str, Any]]:
    """Post-filter safety net (defense in depth)."""
    user_terms = normalize_acl_terms(user_acl_terms)
    return [
        r
        for r in results
        if acl_allows(r.get("acl_terms") or r.get("acl_filter_terms") or [], user_terms)
    ]
