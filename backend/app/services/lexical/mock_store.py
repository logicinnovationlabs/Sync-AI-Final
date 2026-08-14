"""Mock lexical store for testing without OpenSearch."""

from typing import List, Dict, Any, Optional
from app.services.lexical.store import LexicalStore


class MockLexicalStore(LexicalStore):
    """Mock implementation of LexicalStore for testing."""
    
    def __init__(self):
        self.documents = {}
    
    async def index_document(
        self,
        tenant_id: str,
        document_id: str,
        document: Dict[str, Any],
    ) -> None:
        """Mock index document."""
        if tenant_id not in self.documents:
            self.documents[tenant_id] = {}
        self.documents[tenant_id][document_id] = document
    
    async def index_batch(
        self,
        tenant_id: str,
        documents: List[Dict[str, Any]],
    ) -> int:
        """Mock bulk index documents."""
        if tenant_id not in self.documents:
            self.documents[tenant_id] = {}
        for doc in documents:
            doc_id = doc.get("document_id")
            if doc_id:
                self.documents[tenant_id][doc_id] = doc
        return len(documents)
    
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
        """Mock search with proper signature matching abstract interface."""
        # Fail-closed: empty ACL terms return nothing
        if not acl_terms:
            return {"results": [], "facets": {}, "total": 0}
        
        if tenant_id not in self.documents:
            return {"results": [], "facets": {}, "total": 0}
        
        # Simple mock: return documents matching query (case-insensitive substring)
        docs = self.documents[tenant_id]
        results = []
        
        for doc_id, doc_data in docs.items():
            # Check ACL if not wildcard
            if "*" not in acl_terms:
                doc_acl = doc_data.get("acl_filter_terms", [])
                if doc_acl and not any(term in doc_acl for term in acl_terms):
                    continue  # Skip documents user doesn't have access to
            
            # Simple text matching
            if query and query != "*":
                text = f"{doc_data.get('title', '')} {doc_data.get('body_text', '')}".lower()
                if query.lower() not in text:
                    continue
            
            results.append({
                "document_id": doc_id,
                "score": 1.0,
                "title": doc_data.get("title", ""),
                "snippet": doc_data.get("body_text", "")[:200],
                "metadata": {
                    "file_path": doc_data.get("file_path"),
                    "source": doc_data.get("source"),
                    "language": doc_data.get("language"),
                }
            })
        
        # Apply pagination
        total = len(results)
        results = results[from_:from_ + size]
        
        # Mock facets (if requested)
        facets_result = {}
        if facets:
            for facet_field in facets:
                facet_counts = {}
                for doc in docs.values():
                    value = doc.get(facet_field)
                    if value:
                        facet_counts[value] = facet_counts.get(value, 0) + 1
                facets_result[facet_field] = [
                    {"value": k, "count": v} for k, v in facet_counts.items()
                ]
        
        return {
            "results": results,
            "facets": facets_result,
            "total": total,
        }
    
    async def delete_document(
        self,
        tenant_id: str,
        document_id: str,
    ) -> None:
        """Mock delete document."""
        if tenant_id in self.documents and document_id in self.documents[tenant_id]:
            del self.documents[tenant_id][document_id]
    
    async def clear_tenant(self, tenant_id: str):
        """Mock clear tenant."""
        if tenant_id in self.documents:
            del self.documents[tenant_id]
