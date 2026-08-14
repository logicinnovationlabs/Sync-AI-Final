"""
OpenSearch-backed lexical store for production use.
Implements BM25 ranking with ACL prefiltering and code-aware tokenization.
"""

import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.lexical.store import LexicalStore

logger = logging.getLogger(__name__)

INDEX_BODY: Dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "1s",
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
                    "pattern": "([A-Z][a-z]+|[a-z]+|_+|[0-9]+)",
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
            "language": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "acl_filter_terms": {"type": "keyword"},
            "deleted": {"type": "boolean"},
        }
    },
}


class OpenSearchLexicalStore(LexicalStore):
    """OpenSearch client with ACL filter clause on every query."""
    
    def __init__(self) -> None:
        try:
            from opensearchpy import OpenSearch
        except ImportError as exc:
            raise RuntimeError(
                "opensearch-py is required for OpenSearch backend"
            ) from exc
        
        http_auth = None
        opensearch_url = getattr(settings, 'opensearch_url', None)
        # Increase timeout to 60 seconds for slow Docker/test environments
        timeout = 60
        
        if opensearch_url:
            # Parse URL for host/port
            self._client = OpenSearch(
                hosts=[opensearch_url],
                http_auth=http_auth,
                use_ssl=True,
                verify_certs=False,
                ssl_show_warn=False,
                timeout=timeout,
            )
        else:
            # Fallback to host/port config
            host = getattr(settings, 'opensearch_host', 'localhost')
            port = getattr(settings, 'opensearch_port', 9200)
            self._client = OpenSearch(
                hosts=[{"host": host, "port": port}],
                http_auth=http_auth,
                timeout=timeout,
            )
        
        self.index_prefix = getattr(settings, 'opensearch_index_prefix', 'snyq')
        logger.info(f"OpenSearchLexicalStore initialized with prefix: {self.index_prefix}")
    
    def _index_name(self, tenant_id: str) -> str:
        """Generate index name for tenant."""
        return f"{self.index_prefix}_lexical_{tenant_id}"
    
    async def search(
        self,
        tenant_id: str,
        query: str,
        acl_terms: List[str],
        filters: Optional[Dict[str, Any]] = None,
        facets: Optional[List[str]] = None,
        from_: int = 0,
        size: int = 20,
    ) -> Dict[str, Any]:
        """Execute BM25 search with ACL prefilter."""
        # CRITICAL: Fail-closed - empty ACL terms should return nothing
        if not acl_terms:
            logger.warning(f"Empty ACL terms for tenant {tenant_id} – returning zero results (fail-closed)")
            return {"results": [], "facets": {}, "total": 0}
        
        index_name = self._index_name(tenant_id)
        
        # Build query with ACL filter
        must_clauses = []
        
        # Handle wildcard query "*" to mean "match all"
        if query and query != "*":
            must_clauses.append({
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "body_text", "file_path^2"],
                    "type": "best_fields",
                }
            })
        
        filter_clauses = [
            {"term": {"tenant_id": tenant_id}},
            {"term": {"deleted": False}},
        ]
        
        # ACL prefilter - handle wildcard "*" to mean "all documents"
        # CRITICAL: Implement deny: semantics
        # 1. Documents with no ACL field are public → ALLOW
        # 2. Documents with deny:* terms matching user ACL → DENY (must_not)
        # 3. Documents with positive ACL terms matching user ACL → ALLOW
        if acl_terms and "*" not in acl_terms:
            # Build deny terms: for each user ACL term, create corresponding deny: version
            deny_terms = [f"deny:{term}" for term in acl_terms]
            
            filter_clauses.append({
                "bool": {
                    "should": [
                        # Allow: positive ACL match
                        {"terms": {"acl_filter_terms": acl_terms}},
                        # Allow: no ACL field (public)
                        {"bool": {"must_not": {"exists": {"field": "acl_filter_terms"}}}}
                    ],
                    "must_not": [
                        # Deny: has deny:* term matching user
                        {"terms": {"acl_filter_terms": deny_terms}}
                    ],
                    "minimum_should_match": 1
                }
            })
        
        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    filter_clauses.append({"terms": {key: value}})
                else:
                    filter_clauses.append({"term": {key: value}})
        
        # Build final query body
        if must_clauses:
            body = {
                "query": {
                    "bool": {
                        "must": must_clauses,
                        "filter": filter_clauses,
                    }
                },
                "from": from_,
                "size": size,
                "highlight": {
                    "fields": {
                        "title": {},
                        "body_text": {"number_of_fragments": 1, "fragment_size": 200},
                    }
                },
            }
        else:
            # No must clauses - use match_all with filters only
            body = {
                "query": {
                    "bool": {
                        "must": [{"match_all": {}}],
                        "filter": filter_clauses,
                    }
                },
                "from": from_,
                "size": size,
            }
        
        # Add facets/aggregations if requested
        if facets:
            body["aggs"] = {
                f"{field}_facet": {"terms": {"field": field, "size": 100}}
                for field in facets
            }
        
        try:
            response = self._client.search(index=index_name, body=body)
        except Exception as e:
            logger.error(f"OpenSearch query failed: {e}")
            return {"results": [], "facets": {}, "total": 0}
        
        # Parse results
        hits = response.get("hits", {}).get("hits", [])
        results = []
        for hit in hits:
            source = hit["_source"]
            highlight = hit.get("highlight", {})
            snippet = highlight.get("body_text", [""])[0] if "body_text" in highlight else ""
            
            results.append({
                "document_id": source["document_id"],
                "score": hit["_score"],
                "title": source.get("title", ""),
                "snippet": snippet,
                "metadata": {
                    "file_path": source.get("file_path"),
                    "source": source.get("source"),
                    "language": source.get("language"),
                }
            })
        
        # Parse facets
        facets_result = {}
        if facets:
            aggs = response.get("aggregations", {})
            for field in facets:
                buckets = aggs.get(f"{field}_facet", {}).get("buckets", [])
                facets_result[field] = [
                    {"value": b["key"], "count": b["doc_count"]}
                    for b in buckets
                ]
        
        return {
            "results": results,
            "facets": facets_result,
            "total": response.get("hits", {}).get("total", {}).get("value", 0),
        }
    
    async def index_document(
        self,
        tenant_id: str,
        document_id: str,
        document: Dict[str, Any],
    ) -> None:
        """Index a single document."""
        index_name = self._index_name(tenant_id)
        
        # Ensure index exists
        if not self._client.indices.exists(index=index_name):
            self._client.indices.create(index=index_name, body=INDEX_BODY)
        
        # Add tenant_id and document_id
        document["tenant_id"] = tenant_id
        document["document_id"] = document_id
        
        self._client.index(
            index=index_name,
            id=document_id,
            body=document,
            refresh=True,
        )
        logger.debug(f"Indexed document {document_id} in {index_name}")
    
    async def index_batch(
        self,
        tenant_id: str,
        documents: List[Dict[str, Any]],
    ) -> int:
        """Bulk index documents."""
        if not documents:
            return 0
        
        index_name = self._index_name(tenant_id)
        
        # Ensure index exists
        if not self._client.indices.exists(index=index_name):
            self._client.indices.create(index=index_name, body=INDEX_BODY)
        
        # Build bulk request
        bulk_body = []
        for doc in documents:
            # Create a copy to avoid mutating the original
            doc_copy = doc.copy()
            doc_copy["tenant_id"] = tenant_id
            bulk_body.append({"index": {"_index": index_name, "_id": doc_copy["document_id"]}})
            bulk_body.append(doc_copy)
        
        response = self._client.bulk(body=bulk_body, refresh=True)
        
        if response.get("errors"):
            logger.error("Bulk indexing had errors")
        
        return len(documents)
    
    async def delete_document(
        self,
        tenant_id: str,
        document_id: str,
    ) -> None:
        """Delete a document from the index."""
        index_name = self._index_name(tenant_id)
        
        try:
            self._client.delete(index=index_name, id=document_id, refresh=True)
            logger.debug(f"Deleted document {document_id} from {index_name}")
        except Exception as e:
            logger.warning(f"Failed to delete document {document_id}: {e}")
    
    async def refresh_index(self, tenant_id: str) -> None:
        """Force refresh the index to make recent changes visible."""
        index_name = self._index_name(tenant_id)
        try:
            self._client.indices.refresh(index=index_name)
            logger.debug(f"Refreshed index {index_name}")
        except Exception as e:
            logger.warning(f"Failed to refresh index {index_name}: {e}")
    
    async def delete_index(self, tenant_id: str) -> None:
        """Delete the entire index for a tenant."""
        index_name = self._index_name(tenant_id)
        try:
            if self._client.indices.exists(index=index_name):
                self._client.indices.delete(index=index_name)
                logger.info(f"Deleted index {index_name}")
        except Exception as e:
            logger.warning(f"Failed to delete index {index_name}: {e}")
