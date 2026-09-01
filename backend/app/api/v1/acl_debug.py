"""ACL debugging endpoints to diagnose indexing/querying mismatches.

These endpoints help verify ACL term generation and document visibility.
Enable in development/testing only.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user, require_scope
from app.acl.filter import acl_terms_from_jwt, document_is_visible
from app.acl.term_generator import generate_acl_terms_for_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/debug", tags=["acl-debug"])


class ACLTermsResponse(BaseModel):
    """Response showing ACL terms from different sources."""

    from_jwt: List[str]
    from_generator: List[str]
    match: bool
    missing_in_jwt: List[str]
    missing_in_generator: List[str]


class DocumentVisibilityRequest(BaseModel):
    """Request to check if a document is visible to the user."""

    document_acl_terms: List[str]


class DocumentVisibilityResponse(BaseModel):
    """Response showing document visibility analysis."""

    visible: bool
    user_acl_terms: List[str]
    document_acl_terms: List[str]
    matching_terms: List[str]
    explanation: str


@router.get("/acl/my-terms", response_model=ACLTermsResponse)
async def get_my_acl_terms(
    current_user: Dict[str, Any] = Depends(require_scope("search.read")),
):
    """
    Show ACL terms extracted from your JWT vs. what would be indexed.

    Useful for diagnosing ACL mismatch between indexing and querying.
    The 'from_jwt' and 'from_generator' lists should be identical for
    documents to be visible.
    """
    # Extract from JWT (query-time)
    jwt_terms = acl_terms_from_jwt(current_user)

    # Generate using unified generator (index-time)
    principal_id = str(
        current_user.get("principal_id")
        or current_user.get("user_id")
        or current_user.get("sub")
        or ""
    )
    email = str(current_user.get("email") or "").strip()
    groups = current_user.get("groups") or []

    generated_terms = generate_acl_terms_for_user(
        principal_id=principal_id, email=email, groups=groups
    )

    # Compare
    jwt_set = set(jwt_terms)
    gen_set = set(generated_terms)

    return ACLTermsResponse(
        from_jwt=jwt_terms,
        from_generator=generated_terms,
        match=jwt_set == gen_set,
        missing_in_jwt=sorted(gen_set - jwt_set),
        missing_in_generator=sorted(jwt_set - gen_set),
    )


@router.post("/acl/check-visibility", response_model=DocumentVisibilityResponse)
async def check_document_visibility(
    body: DocumentVisibilityRequest,
    current_user: Dict[str, Any] = Depends(require_scope("search.read")),
):
    """
    Check if a document with given ACL terms would be visible to you.

    Simulates the search-time ACL filter to verify document visibility.
    """
    user_acl = acl_terms_from_jwt(current_user)
    doc_acl = body.document_acl_terms

    visible = document_is_visible(user_acl, doc_acl)

    # Find matching terms
    user_set = set(user_acl)
    doc_positive = set(t for t in doc_acl if not t.startswith("deny:"))
    matching = sorted(user_set & doc_positive)

    if visible:
        explanation = f"Document is visible. {len(matching)} matching ACL term(s): {matching}"
    else:
        explanation = "Document is NOT visible. "
        if not doc_positive:
            explanation += "Document has no positive ACL terms (private)."
        elif not user_acl:
            explanation += "Your JWT has no ACL terms (fail-closed)."
        else:
            deny_terms = [t for t in doc_acl if t.startswith("deny:")]
            if any(t.replace("deny:", "") in user_set or t in user_set for t in deny_terms):
                explanation += f"Explicit deny applies: {deny_terms}"
            else:
                explanation += f"No matching ACL terms. Need one of: {sorted(doc_positive)}"

    return DocumentVisibilityResponse(
        visible=visible,
        user_acl_terms=user_acl,
        document_acl_terms=doc_acl,
        matching_terms=matching,
        explanation=explanation,
    )


@router.get("/acl/health")
async def acl_debug_health():
    """Health check for ACL debug endpoints."""
    return {"status": "ok", "service": "acl_debug"}
