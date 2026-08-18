"""In-process Block J federator entry. Block M must not HTTP-hop (§29.5)."""

from __future__ import annotations

from typing import Any, Dict

from app.models.federated import UserContext


async def federated_search_inprocess(
    *,
    query: str,
    tenant_id: str,
    principal_id: str,
    size: int = 20,
) -> Dict[str, Any]:
    """Call Block J's federator helpers in-process (same process, no HTTP)."""
    from app.api.v1.search.federated import (
        _merge_and_rank,
        _safe_call_lexical,
        _safe_call_vector,
    )

    user_ctx = UserContext(
        tenant_id=tenant_id,
        principal_id=principal_id,
        groups=[],
        scopes=[],
    )
    acl_terms = user_ctx.build_acl_terms()
    lexical_results, lex_status = await _safe_call_lexical(query, tenant_id, acl_terms, size)
    vector_results, vec_status = await _safe_call_vector(query, tenant_id, acl_terms, size)
    merged = _merge_and_rank(lexical_results, vector_results, size)
    degraded = not (lex_status.ok and vec_status.ok)
    return {
        "results": [item.model_dump() for item in merged],
        "total": len(merged),
        "degraded": degraded,
        "backends": [lex_status.model_dump(), vec_status.model_dump()],
        "query": query,
    }
