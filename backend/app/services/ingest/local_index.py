"""Process-local hybrid index so federated search can see Google backfill
without requiring OpenSearch/Qdrant to be up in every local environment.
"""

from __future__ import annotations

from typing import Any, Dict, List


class LocalIngestIndex:
    def __init__(self) -> None:
        self._docs: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def upsert(self, tenant_id: str, document: Dict[str, Any]) -> None:
        doc_id = str(document.get("document_id") or document.get("id") or "")
        if not tenant_id or not doc_id:
            return
        self._docs.setdefault(tenant_id, {})[doc_id] = dict(document)

    def search(
        self,
        tenant_id: str,
        query: str,
        acl_terms: List[str],
        size: int = 20,
    ) -> List[Dict[str, Any]]:
        if not acl_terms:
            return []
        bucket = self._docs.get(tenant_id) or {}
        q = (query or "").strip().lower()
        hits: List[Dict[str, Any]] = []
        for doc in bucket.values():
            acls = [str(a) for a in (doc.get("acl_terms") or [])]
            if acls and "*" not in acl_terms:
                if not any(term in acls for term in acl_terms):
                    continue
            blob = f"{doc.get('title', '')} {doc.get('body_text') or doc.get('content') or ''}".lower()
            if q and q != "*" and q not in blob:
                continue
            hits.append(
                {
                    "document_id": doc.get("document_id") or doc.get("id"),
                    "score": 1.0,
                    "title": doc.get("title") or "",
                    "snippet": (doc.get("body_text") or doc.get("content") or "")[:240],
                    "sources": ["local_ingest"],
                }
            )
            if len(hits) >= size:
                break
        return hits


local_ingest_index = LocalIngestIndex()
