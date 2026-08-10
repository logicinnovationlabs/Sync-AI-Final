"""POST /_internal/index — index writer client for Block C / tests."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import assert_tenant_binding, get_current_user
from app.models.document import IndexDocumentRequest, IndexDocumentResponse
from app.services.factory import get_lexical_store
from app.services.lexical_store import LexicalStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["index"])


class IndexBatchRequest(BaseModel):
    documents: List[IndexDocumentRequest] = Field(default_factory=list)


def get_store() -> LexicalStore:
    return get_lexical_store()


async def _index_one(store: LexicalStore, doc: IndexDocumentRequest) -> str:
    await store.index_document(
        tenant_id=doc.tenant_id,
        document_id=doc.document_id,
        fields=doc.fields,
        deleted=doc.deleted,
    )
    return doc.document_id


@router.post("/_internal/index", response_model=IndexDocumentResponse)
async def index_documents(
    body: Union[IndexDocumentRequest, IndexBatchRequest, Dict[str, Any]],
    current_user: Dict[str, Any] = Depends(get_current_user),
    store: LexicalStore = Depends(get_store),
) -> IndexDocumentResponse:
    """Upsert one document or a batch into the lexical index."""
    token_tenant = str(current_user.get("tenant_id", ""))

    docs: List[IndexDocumentRequest]
    if isinstance(body, IndexBatchRequest):
        docs = body.documents
    elif isinstance(body, IndexDocumentRequest):
        docs = [body]
    elif isinstance(body, dict) and "documents" in body:
        docs = [IndexDocumentRequest(**d) for d in body["documents"]]
    elif isinstance(body, dict):
        docs = [IndexDocumentRequest(**body)]
    else:
        raise HTTPException(status_code=400, detail="Invalid index payload")

    if not docs:
        raise HTTPException(status_code=400, detail="No documents to index")

    tenant_id = docs[0].tenant_id
    for d in docs:
        if d.tenant_id != tenant_id:
            raise HTTPException(status_code=400, detail="Mixed tenant_id in batch")
        assert_tenant_binding(d.tenant_id, token_tenant)
        if "acl_filter_terms" not in d.fields and "acl_terms" not in d.fields:
            raise HTTPException(
                status_code=400,
                detail=f"acl_filter_terms required for document {d.document_id}",
            )

    ids: List[str] = []
    for d in docs:
        ids.append(await _index_one(store, d))

    logger.info("Indexed %d docs for tenant %s", len(ids), tenant_id)
    return IndexDocumentResponse(indexed=len(ids), tenant_id=tenant_id, document_ids=ids)


@router.delete("/_internal/index/{tenant_id}/{document_id}")
async def delete_document(
    tenant_id: str,
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    store: LexicalStore = Depends(get_store),
) -> Dict[str, Any]:
    assert_tenant_binding(tenant_id, str(current_user.get("tenant_id", "")))
    await store.delete_document(tenant_id, document_id)
    return {"deleted": True, "document_id": document_id, "tenant_id": tenant_id}