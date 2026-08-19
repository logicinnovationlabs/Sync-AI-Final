"""Single search-time ACL filter (deny-override).

Index-time compilation lives in ``app.acl.compiler``. Every search backend
(F lexical, G vector, J federated, L assistant) must apply this module so an
explicit deny cannot leak through a ``MatchAny``/terms allow-list.

Term conventions (stored on the document/chunk):
  ``user:alice`` / ``group:eng``  — allow
  ``deny:user:bob``               — explicit deny of that principal/group

Fail-closed: empty caller ACL → no documents.
``*`` is a test/ops bypass (used by Block G recall harnesses).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Mapping

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
    if not terms:
        return True

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
            "should": [
                {"terms": {field: list(user_acl)}},
                {"bool": {"must_not": {"exists": {"field": field}}}},
            ],
            "must_not": [{"terms": {field: deny}}] if deny else [],
            "minimum_should_match": 1,
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

    groups = payload.get("groups") or []
    if isinstance(groups, (list, tuple)):
        for group in groups:
            _add(group)
            group_str = str(group)
            if group_str and not group_str.startswith("group:"):
                _add(f"group:{group_str}")

    return terms
