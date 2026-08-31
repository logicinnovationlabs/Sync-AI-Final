"""Bridge from Google connector raw objects into Block C Pipeline.process_raw()."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.base_connector import UnifiedDocument

logger = logging.getLogger(__name__)

# Max concurrent pipeline.process_raw() calls per batch.
# Set to 4 to safely fit within database session pool limits (e.g. Supabase pool_size: 15)
# with 2 Celery workers (4 * 2 = 8 connections max).
_PIPELINE_CONCURRENCY = 4

_memory_pipeline = None


def _build_pipeline(repo):
    from app.services.pipeline import Pipeline
    from app.normalizer.registry import normalizer_registry
    from app.identity.resolver import IdentityResolver
    from app.identity.matchers.email_matcher import EmailMatcher
    from app.identity.matchers.username_matcher import UsernameMatcher
    from app.acl.compiler import ACLCompiler
    from app.acl.container_service import ContainerService
    import app.normalizer.strategies  # noqa: F401 — register strategies

    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    compiler = ACLCompiler(resolver, ContainerService(repo), repo)
    return Pipeline(normalizer_registry, resolver, compiler, repo)


def get_pipeline(session=None):
    """Build a Block C pipeline.

    Production/backfill pass a tenant DB session (Postgres CanonicalRepo),
    matching ``CanonicalRepo(use_memory=False, session=db_session)`` used by
    ``/identity/resolve`` and ``/acl/{id}``. Memory repo is only a test fallback
    when no session is available.
    """
    from app.storage.canonical_repo import CanonicalRepo

    if session is not None:
        repo = CanonicalRepo(use_memory=False, session=session)
        return _build_pipeline(repo)

    global _memory_pipeline
    if _memory_pipeline is not None:
        return _memory_pipeline
    repo = CanonicalRepo(use_memory=True)
    _memory_pipeline = _build_pipeline(repo)
    return _memory_pipeline


async def _run_pipeline(
    raw_documents: List[Dict[str, Any]],
    source_type: str,
    tenant_uuid: UUID,
    tenant_id: str,
    *,
    session_factory=None,
    pipeline=None,
) -> Optional[List[UnifiedDocument]]:
    sem = asyncio.Semaphore(_PIPELINE_CONCURRENCY)
    failures = 0

    async def _process_one(raw: Dict[str, Any]) -> Optional[UnifiedDocument]:
        nonlocal failures
        async with sem:
            try:
                if session_factory is not None:
                    async with session_factory() as session:
                        pipe = get_pipeline(session=session)
                        result = await pipe.process_raw(raw, source_type, tenant_uuid)
                else:
                    pipe = pipeline or get_pipeline()
                    result = await pipe.process_raw(raw, source_type, tenant_uuid)
                return result.get("unified_document") if isinstance(result, dict) else None
            except Exception as item_err:
                failures += 1
                logger.warning(
                    "pipeline=block_c_item_failed source=%s id=%s exc_type=%s exc=%s",
                    source_type,
                    raw.get("id"),
                    type(item_err).__name__,
                    item_err,
                )
                return None

    results = await asyncio.gather(*[_process_one(raw) for raw in raw_documents])
    unified: List[UnifiedDocument] = [doc for doc in results if doc is not None]

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



async def process_raw_batch(
    raw_documents: List[Dict[str, Any]],
    source_type: str,
    tenant_id: str,
    *,
    require_postgres: bool = False,
) -> Optional[List[UnifiedDocument]]:
    """
    Run Block C on each raw object. Returns UnifiedDocuments or None on failure
    so the caller can fall back to connector.transform().

    ``require_postgres=True`` (webhook path): never fall back to in-memory
    CanonicalRepo. Raise instead so Celery retries and nothing is mistaken
    for a successful ACL persist. Backfill keeps the default False.

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

    # Extract base tenant_id from composite format (tenant_id:user_id)
    base_tenant_id = tenant_id
    if ":" in tenant_id:
        parts = tenant_id.split(":")
        if len(parts) == 2:
            base_tenant_id = parts[0]
    
    try:
        tenant_uuid = UUID(str(base_tenant_id))
    except (TypeError, ValueError) as extra:
        if require_postgres:
            raise
        logger.warning(
            "pipeline=fallback_transform source=%s tenant=%s reason=invalid_tenant_id "
            "exc_type=%s exc=%s",
            source_type,
            tenant_id,
            type(extra).__name__,
            extra,
        )
        return None

    from app.core.exceptions import TenantNotFoundError
    from app.services.tenant_resolver import tenant_resolver
    from app.storage.tenant_db import tenant_db_manager

    routing = None
    try:
        routing = await tenant_resolver.resolve(str(base_tenant_id))
    except TenantNotFoundError:
        if require_postgres:
            raise
        routing = None
    except Exception as extra:
        if require_postgres:
            raise
        logger.warning(
            "pipeline postgres routing failed tenant=%s exc_type=%s exc=%s",
            tenant_id,
            type(extra).__name__,
            extra,
        )
        routing = None

    if routing is not None:
        factory = tenant_db_manager.get_session_factory(
            routing.db_host,
            routing.db_name,
            routing.db_user,
            routing.db_password,
            str(routing.tenant_id),
        )
        return await _run_pipeline(
            raw_documents,
            source_type,
            tenant_uuid,
            tenant_id,
            session_factory=factory,
        )

    if require_postgres:
        raise RuntimeError(
            f"webhook ACL compile aborted: postgres routing unavailable tenant={tenant_id}"
        )

    logger.info(
        "pipeline postgres unavailable tenant=%s; using in-memory CanonicalRepo",
        tenant_id,
    )
    try:
        pipeline = get_pipeline()
    except Exception as extra:
        logger.warning(
            "pipeline=fallback_transform source=%s tenant=%s reason=pipeline_init_failed "
            "exc_type=%s exc=%s",
            source_type,
            tenant_id,
            type(extra).__name__,
            extra,
        )
        return None
    return await _run_pipeline(
        raw_documents,
        source_type,
        tenant_uuid,
        tenant_id,
        pipeline=pipeline,
    )
