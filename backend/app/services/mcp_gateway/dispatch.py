"""Route MCP tools to Block J federator or Block K document reader, in-process."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException

from app.core.config import settings
from app.services.document_reader.reader import build_document_payload, read_document
from app.services.query_federator import federated_search_inprocess

SEARCH_TOOLS = frozenset({"search", "federated_search"})
READ_TOOLS = frozenset({"read_document", "document.read", "get_document"})


async def dispatch_tool(
    *,
    tool_name: str,
    arguments: Dict[str, Any],
    tenant_id: str,
    principal_id: str,
) -> Dict[str, Any]:
    if tool_name in SEARCH_TOOLS:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="search requires arguments.query")
        size = int(arguments.get("size") or 20)
        return await federated_search_inprocess(
            query=query,
            tenant_id=tenant_id,
            principal_id=principal_id,
            size=max(1, min(size, 100)),
        )

    if tool_name in READ_TOOLS:
        doc_id = str(arguments.get("document_id") or arguments.get("doc_id") or "").strip()
        if not doc_id:
            raise HTTPException(status_code=400, detail="read_document requires arguments.document_id")
        # NOTE: Document reads delegate to Block K's document_reader, which
        # currently resolves to MockACLChecker (in-memory allow-set) on the
        # real request path, not app.acl.compiler's policy-derived decisions.
        # This is a known, separately-tracked gap — Block M does not introduce
        # a new permission model (architecture §15.1 rule 6), it inherits
        # whatever Block K enforces today. See BUILD_PASS_M_2026-08-17.md.
        import app.api.v1.document as document_routes

        meta, body, _stream = await read_document(
            document_routes.store,
            document_routes.acl_checker,
            tenant_id,
            doc_id,
            principal_id,
            settings.stream_threshold_bytes,
        )
        text = (body or b"").decode("utf-8", errors="replace")
        structured = await document_routes.store.get_structured_metadata(tenant_id, doc_id)
        return build_document_payload(
            doc_id=doc_id,
            tenant_id=tenant_id,
            visible_metadata=meta,
            body=text,
            structured_data=structured,
        )

    raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")
