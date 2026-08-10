"""In-memory BM25 lexical store for Phase 1 signoff (and local dev)."""

from __future__ import annotations

import math
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config import settings
from app.services.acl_filter import acl_allows, filter_results_by_acl, normalize_acl_terms
from app.services.facets import compute_facets
from app.services.lexical_store import LexicalStore
from app.services.metrics import record_index_docs
from app.services.snippets import generate_snippet
from app.services.tokenizer import tokenize


class BM25Index:
    """Simple Okapi BM25 over an in-memory corpus."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_tokens: Dict[str, List[str]] = {}
        self.doc_len: Dict[str, int] = {}
        self.df: Dict[str, int] = defaultdict(int)
        self.avgdl: float = 0.0
        self.n_docs: int = 0

    def add(self, doc_id: str, tokens: List[str]) -> None:
        self.remove(doc_id)
        self.doc_tokens[doc_id] = tokens
        self.doc_len[doc_id] = len(tokens)
        seen: Set[str] = set()
        for t in tokens:
            if t not in seen:
                self.df[t] += 1
                seen.add(t)
        self.n_docs = len(self.doc_tokens)
        total = sum(self.doc_len.values())
        self.avgdl = total / self.n_docs if self.n_docs else 0.0

    def remove(self, doc_id: str) -> None:
        if doc_id not in self.doc_tokens:
            return
        old = self.doc_tokens.pop(doc_id)
        self.doc_len.pop(doc_id, None)
        seen: Set[str] = set()
        for t in old:
            if t not in seen:
                self.df[t] = max(0, self.df[t] - 1)
                if self.df[t] == 0:
                    del self.df[t]
                seen.add(t)
        self.n_docs = len(self.doc_tokens)
        total = sum(self.doc_len.values())
        self.avgdl = total / self.n_docs if self.n_docs else 0.0

    def score(self, query_tokens: List[str], doc_id: str) -> float:
        if doc_id not in self.doc_tokens or not query_tokens or self.n_docs == 0:
            return 0.0
        tokens = self.doc_tokens[doc_id]
        tf_map: Dict[str, int] = defaultdict(int)
        for t in tokens:
            tf_map[t] += 1
        dl = self.doc_len[doc_id]
        score = 0.0
        for qt in query_tokens:
            if qt not in tf_map:
                continue
            df = self.df.get(qt, 0)
            if df <= 0:
                continue
            idf = math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))
            tf = tf_map[qt]
            denom = tf + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1.0))
            score += idf * (tf * (self.k1 + 1)) / denom
        return score


def _matches_filters(doc: Dict[str, Any], filters: Optional[Dict[str, Any]]) -> bool:
    if not filters:
        return True
    for key in ("object_type", "source", "repository", "owner", "language"):
        values = filters.get(key)
        if values:
            if doc.get(key) not in values:
                return False
    tags = filters.get("tags")
    if tags:
        doc_tags = set(doc.get("tags") or [])
        if not doc_tags.intersection(tags):
            return False
    prefix = filters.get("file_path_prefix")
    if prefix:
        path = doc.get("file_path") or ""
        if not path.startswith(prefix):
            return False
    ext = filters.get("extension")
    if ext:
        path = doc.get("file_path") or ""
        if not path.endswith(ext if ext.startswith(".") else f".{ext}"):
            return False
    return True


class MockLexicalStore(LexicalStore):
    """
    In-memory BM25 with ACL applied BEFORE scoring (filter context semantics).

    Documents with deleted=True are excluded from search.
    """

    def __init__(self) -> None:
        # tenant_id -> document_id -> record
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._bm25: Dict[str, BM25Index] = {}
        self._indexed_at: Dict[str, Dict[str, float]] = {}

    async def ensure_tenant(self, tenant_id: str) -> None:
        self._data.setdefault(tenant_id, {})
        self._bm25.setdefault(tenant_id, BM25Index())
        self._indexed_at.setdefault(tenant_id, {})

    async def clear_tenant(self, tenant_id: str) -> None:
        self._data.pop(tenant_id, None)
        self._bm25.pop(tenant_id, None)
        self._indexed_at.pop(tenant_id, None)

    def _field_text(self, fields: Dict[str, Any]) -> str:
        parts = [
            str(fields.get("title") or ""),
            str(fields.get("body_text") or ""),
            str(fields.get("comments_text") or ""),
            str(fields.get("file_path") or ""),
            str(fields.get("container_path") or ""),
        ]
        tags = fields.get("tags") or []
        if isinstance(tags, list):
            parts.append(" ".join(str(t) for t in tags))
        return " ".join(parts)

    async def index_document(
        self,
        tenant_id: str,
        document_id: str,
        fields: Dict[str, Any],
        *,
        deleted: bool = False,
    ) -> None:
        await self.ensure_tenant(tenant_id)
        acl = normalize_acl_terms(fields.get("acl_filter_terms") or fields.get("acl_terms") or [])
        record = {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "title": fields.get("title") or "",
            "body_text": fields.get("body_text") or "",
            "comments_text": fields.get("comments_text") or "",
            "file_path": fields.get("file_path") or "",
            "repository": fields.get("repository") or "",
            "object_type": fields.get("object_type") or "",
            "source": fields.get("source") or "",
            "owner": fields.get("owner") or "",
            "updated_at": fields.get("updated_at"),
            "container_path": fields.get("container_path") or "",
            "language": fields.get("language") or "",
            "tags": list(fields.get("tags") or []),
            "acl_filter_terms": acl,
            "hidden_fields": list(fields.get("hidden_fields") or []),
            "deleted": bool(deleted or fields.get("deleted")),
        }
        self._data[tenant_id][document_id] = record
        self._indexed_at[tenant_id][document_id] = time.perf_counter()

        bm25 = self._bm25[tenant_id]
        if record["deleted"] or not acl:
            bm25.remove(document_id)
        else:
            tokens = tokenize(self._field_text(record))
            bm25.add(document_id, tokens)
        record_index_docs(1)

    async def delete_document(self, tenant_id: str, document_id: str) -> None:
        bucket = self._data.get(tenant_id, {})
        if document_id in bucket:
            bucket[document_id]["deleted"] = True
            self._bm25.get(tenant_id, BM25Index()).remove(document_id)

    async def get_document(
        self, tenant_id: str, document_id: str
    ) -> Optional[Dict[str, Any]]:
        return self._data.get(tenant_id, {}).get(document_id)

    def indexed_at(self, tenant_id: str, document_id: str) -> Optional[float]:
        return self._indexed_at.get(tenant_id, {}).get(document_id)

    async def search(
        self,
        tenant_id: str,
        query: str,
        acl_terms: List[str],
        *,
        filters: Optional[Dict[str, Any]] = None,
        facets: Optional[List[str]] = None,
        from_: int = 0,
        size: int = 20,
    ) -> Dict[str, Any]:
        await self.ensure_tenant(tenant_id)
        user_terms = normalize_acl_terms(acl_terms)
        # Fail-closed: empty ACL => zero results (ACL before retrieval)
        if not user_terms:
            return {"results": [], "facets": {}, "total": 0}

        bucket = self._data[tenant_id]
        bm25 = self._bm25[tenant_id]
        query_tokens = tokenize(query)

        # PREFILTER: ACL + deleted + structured filters BEFORE scoring
        candidates: List[str] = []
        for doc_id, doc in bucket.items():
            if doc.get("deleted"):
                continue
            if not acl_allows(doc.get("acl_filter_terms") or [], user_terms):
                continue
            if not _matches_filters(doc, filters):
                continue
            candidates.append(doc_id)

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for doc_id in candidates:
            doc = bucket[doc_id]
            score = bm25.score(query_tokens, doc_id) if query_tokens else 0.0
            # Match-all / empty query: still return ACL-filtered docs with base score
            if not query_tokens:
                score = 1.0
            snippet = generate_snippet(
                doc["title"],
                doc["body_text"],
                doc["comments_text"],
                query,
                max_chars=settings.snippet_max_chars,
                redact_fields=doc.get("hidden_fields") or [],
            )
            scored.append(
                (
                    score,
                    {
                        "document_id": doc_id,
                        "score": score,
                        "title": doc["title"],
                        "snippet": snippet,
                        "metadata": {
                            "object_type": doc["object_type"],
                            "source": doc["source"],
                            "repository": doc["repository"],
                            "owner": doc["owner"],
                            "language": doc["language"],
                            "tags": doc["tags"],
                            "file_path": doc["file_path"],
                            "container_path": doc["container_path"],
                            "updated_at": doc.get("updated_at"),
                        },
                        "acl_filter_terms": doc["acl_filter_terms"],
                    },
                )
            )

        scored.sort(key=lambda t: t[0], reverse=True)
        total = len(scored)
        page = [item for _, item in scored[from_ : from_ + size]]

        # Defense in depth
        page = filter_results_by_acl(page, user_terms)

        facet_docs = [bucket[d] for d in candidates]
        facet_out = compute_facets(facet_docs, facets or []) if facets else {}

        return {"results": page, "facets": facet_out, "total": total}
