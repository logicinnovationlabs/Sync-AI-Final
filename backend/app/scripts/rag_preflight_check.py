"""Rule #1 — Pre-flight sanity check.

Before tracing a single query, answer one question directly against the
vector store: does the target collection actually contain points for this
tenant/document?

If this returns 0, stop — the bug is in indexing or collection naming,
not retrieval, and Rule #2's trace will waste time proving something
you could have confirmed in one call.

Usage::

    python -m app.scripts.rag_preflight_check --tenant-id TENANT_UUID [--source-type google_drive]
"""

from __future__ import annotations

import argparse
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _build_collection_name(tenant_id: str, prefix: str = "snyq") -> str:
    """Mirror QdrantVectorStore._collection_name logic."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tenant_id)
    return f"{prefix}_{safe}_vectors"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rule #1: Pre-flight sanity check against Qdrant vector store"
    )
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID to check")
    parser.add_argument(
        "--source-type",
        default=None,
        help="Optional source_type filter (e.g. google_drive)",
    )
    parser.add_argument(
        "--document-id",
        default=None,
        help="Optional document_id to check for specific document",
    )
    args = parser.parse_args()

    # ---- Load settings ----
    try:
        from app.core.config import settings
    except Exception as exc:
        logger.error("Could not load settings: %s", exc)
        sys.exit(2)

    # ---- Connect to Qdrant ----
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qm
    except ImportError:
        logger.error("qdrant-client package not installed")
        sys.exit(2)

    qdrant_url = getattr(settings, "qdrant_url", None)
    qdrant_host = getattr(settings, "qdrant_host", "localhost")
    qdrant_port = getattr(settings, "qdrant_port", 6333)
    prefix = getattr(settings, "qdrant_collection_prefix", "snyq")

    if qdrant_url:
        client = QdrantClient(url=qdrant_url, timeout=30)
    else:
        client = QdrantClient(host=qdrant_host, port=qdrant_port, timeout=30)

    # ---- Check Block G per-tenant collection ----
    collection_name = _build_collection_name(args.tenant_id, prefix)
    logger.info("Checking per-tenant collection: %s", collection_name)

    try:
        collections = [c.name for c in client.get_collections().collections]
    except Exception as exc:
        logger.error("Failed to list collections: %s", exc)
        sys.exit(2)

    if collection_name not in collections:
        logger.error(
            "Collection %s does NOT exist. Available: %s",
            collection_name,
            ", ".join(collections) or "(none)",
        )
        logger.error("Bug is in indexing or collection naming, not retrieval.")
        sys.exit(1)

    # ---- Count points with filters ----
    must_conditions = [
        qm.FieldCondition(
            key="tenant_id",
            match=qm.MatchValue(value=args.tenant_id),
        )
    ]

    if args.source_type:
        must_conditions.append(
            qm.FieldCondition(
                key="metadata.source_type",
                match=qm.MatchValue(value=args.source_type),
            )
        )

    if args.document_id:
        must_conditions.append(
            qm.FieldCondition(
                key="document_id",
                match=qm.MatchValue(value=args.document_id),
            )
        )

    try:
        count_result = client.count(
            collection_name=collection_name,
            count_filter=qm.Filter(must=must_conditions),
        )
        count = count_result.count
    except Exception as exc:
        logger.error("Count query failed: %s", exc)
        sys.exit(2)

    filter_desc = f"tenant_id={args.tenant_id}"
    if args.source_type:
        filter_desc += f", source_type={args.source_type}"
    if args.document_id:
        filter_desc += f", document_id={args.document_id}"

    if count == 0:
        logger.error(
            "ZERO points found for %s in collection %s",
            filter_desc,
            collection_name,
        )
        logger.error(
            "Bug is in INDEXING or COLLECTION NAMING, not retrieval. "
            "Do NOT proceed with Rule #2 debug trace."
        )
        sys.exit(1)
    else:
        logger.info(
            "Found %d points for %s in collection %s",
            count,
            filter_desc,
            collection_name,
        )

    # ---- Also check the Block B 'documents' collection ----
    block_b_collection = getattr(settings, "qdrant_collection_name", "documents")
    if block_b_collection in collections:
        try:
            b_count = client.count(
                collection_name=block_b_collection,
                count_filter=qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="tenant_id",
                            match=qm.MatchValue(value=args.tenant_id),
                        )
                    ]
                ),
            ).count
            logger.info(
                "Block B '%s' collection: %d points for tenant %s",
                block_b_collection,
                b_count,
                args.tenant_id,
            )
        except Exception as exc:
            logger.warning("Block B collection check failed: %s", exc)

    logger.info("Pre-flight OK — proceed with Rule #2 debug trace.")
    sys.exit(0)


if __name__ == "__main__":
    main()
