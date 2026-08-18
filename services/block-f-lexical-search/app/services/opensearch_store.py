"""OpenSearch-backed lexical store (Phase 2 / production path)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.acl_filter import (
    build_opensearch_acl_filter,
    filter_results_by_acl,
    normalize_acl_terms,
)
from app.services.facets import FACET_FIELDS
from app.services.lexical_store import LexicalStore
from app.services.metrics import record_index_docs
from app.services.snippets import generate_snippet

logger = logging.getLogger(__name__)

INDEX_BODY: Dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": settings.refresh_interval,
        "analysis": {
            "analyzer": {
                "code_analyzer": {
                    "type": "custom",
                    "tokenizer": "code_tokenizer",
                    "filter": ["lowercase"],
                }
            },
            "tokenizer": {
                "code_tokenizer": {
                    "type": "pattern",
                    # group=1: emit capturing-group matches as tokens. Default
                    # group=-1 treats the pattern as a delimiter and drops them.
                    "pattern": "([A-Z][a-z]+|[a-z]+|_+|[0-9]+)",
                    "group": 1,
                }
            },
        },
    },
    "mappings": {
        "properties": {
            "tenant_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "code_analyzer",
                "fields": {"standard": {"type": "text", "analyzer": "standard"}},
            },
            "body_text": {
                "type": "text",
                "analyzer": "code_analyzer",
                "fields": {"standard": {"type": "text", "analyzer": "standard"}},
            },
            "comments_text": {"type": "text", "analyzer": "code_analyzer"},
            "file_path": {
                "type": "text",
                "analyzer": "code_analyzer",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "repository": {"type": "keyword"},
            "object_type": {"type": "keyword"},
            "source": {"type": "keyword"},
            "owner": {"type": "keyword"},
            "updated_at": {"type": "date"},
            "container_path": {"type": "text", "analyzer": "code_analyzer"},
            "language": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "acl_filter_terms": {"type": "keyword"},
            "hidden_fields": {"type": "keyword"},
            "deleted": {"type": "boolean"},
        }
    },
}


class OpenSearchLexicalStore(LexicalStore):
    """OpenSearch client with ACL filter clause on every query."""

    def __init__(self) -> None:
        try:
            from opensearchpy import OpenSearch
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "opensearch-py is required when SEARCH_BACKEND=opensearch"
            ) from exc

        http_auth = None
        if settings.opensearch_user and settings.opensearch_password:
            http_auth = (settings.opensearch_user, settings.opensearch_password)

        self._client = OpenSearch(
            hosts=[
                {
                    "host": settings.opensearch_host,
                    "port": settings.opensearch_port,
                }
            ],
            http_auth=http_auth,
            use_ssl=settings.opensearch_use_ssl,
            verify_certs=settings.opensearch_verify_certs,
            timeout=settings.search_timeout_seconds,
        )

    def _index_name(self, tenant_id: str) -> str:
        safe = tenant_id.replace("/", "_").replace(" ", "_").lower()
        return f"{settings.index_prefix}-{safe}"

    async def ensure_tenant(self, tenant_id: str) -> None:
        index = self._index_name(tenant_id)
        if not self._client.indices.exists(index=index):
            body = dict(INDEX_BODY)
            body["settings"] = dict(INDEX_BODY["settings"])
            body["settings"]["refresh_interval"] = settings.refresh_interval
            self._client.indices.create(index=index, body=body)
            logger.info("Created lexical index %s", index)

    async def clear_tenant(self, tenant_id: str) -> None:
        index = self._index_name(tenant_id)
        if self._client.indices.exists(index=index):
            self._client.indices.delete(index=index)

    async def index_document(
        self,
        tenant_id: str,
        document_id: str,
        fields: Dict[str, Any],
        *,
        deleted: bool = False,
    ) -> None:
        await self.ensure_tenant(tenant_id)
        acl = normalize_acl_terms(
            fields.get("acl_filter_terms") or fields.get("acl_terms") or []
        )
        body = {
            "tenant_id": tenant_id,
            "document_id": document_id,
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
        self._client.index(
            index=self._index_name(tenant_id),
            id=document_id,
            body=body,
            refresh=True,
        )
        record_index_docs(1)

    async def delete_document(self, tenant_id: str, document_id: str) -> None:
        index = self._index_name(tenant_id)
        if not self._client.indices.exists(index=index):
            return
        # Soft-delete so ACL red-team "deleted document" stays fail-closed
        try:
            self._client.update(
                index=index,
                id=document_id,
                body={"doc": {"deleted": True, "acl_filter_terms": []}},
                refresh=True,
            )
        except Exception:  # noqa: BLE001
            self._client.delete(index=index, id=document_id, ignore=[404], refresh=True)

    async def get_document(
        self, tenant_id: str, document_id: str
    ) -> Optional[Dict[str, Any]]:
        index = self._index_name(tenant_id)
        try:
            res = self._client.get(index=index, id=document_id)
            return res.get("_source")
        except Exception:  # noqa: BLE001
            return None

    def _filter_clauses(self, filters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        clauses: List[Dict[str, Any]] = [{"term": {"deleted": False}}]
        if not filters:
            return clauses
        for key in ("object_type", "source", "repository", "owner", "language", "tags"):
            values = filters.get(key)
            if values:
                clauses.append({"terms": {key: values}})
        prefix = filters.get("file_path_prefix")
        if prefix:
            clauses.append({"prefix": {"file_path.keyword": prefix}})
        ext = filters.get("extension")
        if ext:
            suffix = ext if ext.startswith(".") else f".{ext}"
            clauses.append({"wildcard": {"file_path.keyword": f"*{suffix}"}})
        return clauses

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
        if not user_terms:
            return {"results": [], "facets": {}, "total": 0}

        # CRITICAL: ACL in filter context BEFORE retrieval
        filter_clauses = [build_opensearch_acl_filter(user_terms)]
        filter_clauses.extend(self._filter_clauses(filters))

        must: List[Dict[str, Any]]
        if query and query.strip():
            must = [
                {
                    "multi_match": {
                        "query": query,
                        "fields": [
                            "title^3",
                            "body_text",
                            "comments_text",
                            "file_path",
                            "container_path",
                        ],
                        "type": "best_fields",
                    }
                }
            ]
        else:
            must = [{"match_all": {}}]

        body: Dict[str, Any] = {
            "from": from_,
            "size": size,
            "query": {
                "bool": {
                    "must": must,
                    "filter": filter_clauses,
                }
            },
        }

        if facets:
            body["aggs"] = {}
            for field in facets:
                if field in FACET_FIELDS:
                    # exclude="" matches mock compute_facets (skip empty/None)
                    body["aggs"][field] = {
                        "terms": {"field": field, "size": 100, "exclude": ""}
                    }

        res = self._client.search(index=self._index_name(tenant_id), body=body)
        hits = res.get("hits", {})
        total = hits.get("total", {})
        total_n = total.get("value", 0) if isinstance(total, dict) else int(total or 0)

        results: List[Dict[str, Any]] = []
        for hit in hits.get("hits", []):
            src = hit.get("_source") or {}
            snippet = generate_snippet(
                src.get("title") or "",
                src.get("body_text") or "",
                src.get("comments_text") or "",
                query,
                max_chars=settings.snippet_max_chars,
                redact_fields=src.get("hidden_fields") or [],
            )
            results.append(
                {
                    "document_id": src.get("document_id") or hit.get("_id"),
                    "score": float(hit.get("_score") or 0.0),
                    "title": src.get("title") or "",
                    "snippet": snippet,
                    "metadata": {
                        "object_type": src.get("object_type"),
                        "source": src.get("source"),
                        "repository": src.get("repository"),
                        "owner": src.get("owner"),
                        "language": src.get("language"),
                        "tags": src.get("tags") or [],
                        "file_path": src.get("file_path"),
                        "container_path": src.get("container_path"),
                        "updated_at": src.get("updated_at"),
                    },
                    "acl_filter_terms": src.get("acl_filter_terms") or [],
                }
            )

        results = filter_results_by_acl(results, user_terms)

        facet_out: Dict[str, List[Dict[str, Any]]] = {}
        aggs = res.get("aggregations") or {}
        for field, agg in aggs.items():
            facet_out[field] = [
                {"value": b["key"], "count": b["doc_count"]}
                for b in agg.get("buckets", [])
                if b.get("key") not in (None, "")
            ]

        return {"results": results, "facets": facet_out, "total": total_n}
