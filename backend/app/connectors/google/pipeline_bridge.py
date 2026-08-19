"""Bridge from Google connector raw objects into Block C Pipeline.process_raw()."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.base_connector import UnifiedDocument

logger = logging.getLogger(__name__)

_pipeline = None


def get_pipeline():
    """Lazy singleton Block C pipeline (in-process CanonicalRepo)."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    from app.services.pipeline import Pipeline
    from app.normalizer.registry import normalizer_registry
    from app.identity.resolver import IdentityResolver
    from app.identity.matchers.email_matcher import EmailMatcher
    from app.identity.matchers.username_matcher import UsernameMatcher
    from app.acl.compiler import ACLCompiler
    from app.acl.container_service import ContainerService
    from app.storage.canonical_repo import CanonicalRepo
    import app.normalizer.strategies  # noqa: F401 — register strategies

    repo = CanonicalRepo(use_memory=True)
    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    compiler = ACLCompiler(resolver, ContainerService(repo), repo)
    _pipeline = Pipeline(normalizer_registry, resolver, compiler, repo)
    return _pipeline


async def process_raw_batch(
    raw_documents: List[Dict[str, Any]],
    source_type: str,
    tenant_id: str,
) -> Optional[List[UnifiedDocument]]:
    """
    Run Block C on each raw object. Returns UnifiedDocuments or None on failure
    so the caller can fall back to connector.transform().

    Always logs a visible path marker:
      pipeline=block_c  — Block C produced at least one UnifiedDocument
      pipeline=fallback_transform — Block C did not; caller must transform()
    """
    if not raw_documents:
        logger.info(
            "pipeline=block_c n=0 source=%s tenant=%s (empty batch, nothing to process)",
            source_type,
            tenant_id,
        )
        return []

    try:
        tenant_uuid = UUID(str(tenant_id))
    except (TypeError, ValueError) as exc:
        logger.warning(
            "pipeline=fallback_transform source=%s tenant=%s reason=invalid_tenant_id "
            "exc_type=%s exc=%s",
            source_type,
            tenant_id,
            type(exc).__name__,
            exc,
        )
        return None

    try:
        pipeline = get_pipeline()
    except Exception as exc:
        logger.warning(
            "pipeline=fallback_transform source=%s tenant=%s reason=pipeline_init_failed "
            "exc_type=%s exc=%s",
            source_type,
            tenant_id,
            type(exc).__name__,
            exc,
        )
        return None

    unified: List[UnifiedDocument] = []
    failures = 0
    for raw in raw_documents:
        try:
            result = await pipeline.process_raw(raw, source_type, tenant_uuid)
            doc = result.get("unified_document")
            if doc is not None:
                unified.append(doc)
        except Exception as exc:
            failures += 1
            logger.warning(
                "pipeline=block_c_item_failed source=%s id=%s exc_type=%s exc=%s",
                source_type,
                raw.get("id"),
                type(exc).__name__,
                exc,
            )

    if unified:
        logger.info(
            "pipeline=block_c n=%s failed_items=%s source=%s tenant=%s",
            len(unified),
            failures,
            source_type,
            tenant_id,
        )
        return unified

    logger.warning(
        "pipeline=fallback_transform source=%s tenant=%s reason=no_unified_docs "
        "input_n=%s failed_items=%s",
        source_type,
        tenant_id,
        len(raw_documents),
        failures,
    )
    return None
