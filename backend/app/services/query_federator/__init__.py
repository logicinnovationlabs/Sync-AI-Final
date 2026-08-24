"""In-process Block J federator entry. Block L/M must not HTTP-hop to localhost."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.federated import UserContext


async def federated_search_inprocess(
    *,
    query: str,
    tenant_id: str,
    principal_id: str,
    size: int = 20,
    acl_terms: Optional[List[str]] = None,
    enable_lexical: bool = True,
    enable_vector: bool = True,
) -> Dict[str, Any]:
    """Same backends as POST /search/federated, without an HTTP self-call."""
    from app.api.v1.search.federated import (
        _merge_and_rank,
        _safe_call_indexed,
        _safe_call_lexical,
        _safe_call_vector,
    )

    if acl_terms is None:
        user_ctx = UserContext(
            tenant_id=tenant_id,
            principal_id=principal_id,
            groups=[],
            scopes=[],
        )
        acl_terms = user_ctx.build_acl_terms()
        # Mirror JWT helper: bare id + user:id
        if principal_id and f"user:{principal_id}" not in acl_terms:
            acl_terms = list(acl_terms) + [f"user:{principal_id}"]

    indexed_results, idx_status = await _safe_call_indexed(
        query, tenant_id, acl_terms, size
    )
    lexical_results: List[Dict[str, Any]] = []
    vector_results: List[Dict[str, Any]] = []
    statuses = [idx_status]

    if enable_lexical:
        lexical_results, lex_status = await _safe_call_lexical(
            query, tenant_id, acl_terms, size
        )
        statuses.append(lex_status)
    if enable_vector:
        vector_results, vec_status = await _safe_call_vector(
            query, tenant_id, acl_terms, size
        )
        statuses.append(vec_status)

    merged = _merge_and_rank(
        indexed_results + lexical_results,
        vector_results,
        size,
    )
    degraded = not any(s.ok for s in statuses) or not all(s.ok for s in statuses)
    return {
        "results": [item.model_dump() for item in merged],
        "total": len(merged),
        "degraded": degraded,
        "backends": [s.model_dump() for s in statuses],
        "query": query,
    }
