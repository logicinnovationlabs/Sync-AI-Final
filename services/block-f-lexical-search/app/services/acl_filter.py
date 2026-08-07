"""ACL prefilter helpers for lexical queries — ALWAYS applied BEFORE retrieval."""

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


def acl_allows(doc_acl_terms: List[str], user_acl_terms: List[str]) -> bool:
    """
    True if the user may read the document.

    Rule: non-empty intersection of principal/group IDs.
    Empty document ACL means no access (fail-closed).
    Explicit deny: terms on the document override allow.
    """
    if not doc_acl_terms or not user_acl_terms:
        return False
    denies = {t[5:] for t in doc_acl_terms if t.startswith("deny:")}
    allows = {t for t in doc_acl_terms if not t.startswith("deny:")}
    user = set(user_acl_terms)
    if denies & user:
        return False
    return bool(allows & user)


def build_opensearch_acl_filter(user_acl_terms: List[str]) -> Dict[str, Any]:
    """
    Build OpenSearch filter clause for ACL overlap.

    MUST be placed in the filter context of every search query.
    Never rely on post-filtering alone.
    """
    terms = normalize_acl_terms(user_acl_terms)
    if not terms:
        return {"match_none": {}}
    return {"terms": {"acl_filter_terms": terms}}


def filter_results_by_acl(
    results: List[Dict[str, Any]],
    user_acl_terms: List[str],
) -> List[Dict[str, Any]]:
    """Post-filter safety net (defense in depth — NOT a substitute for prefilter)."""
    user_terms = normalize_acl_terms(user_acl_terms)
    return [
        r
        for r in results
        if acl_allows(r.get("acl_filter_terms") or r.get("acl_terms") or [], user_terms)
    ]
