"""
Blind Indexer: accepts UnifiedDocument, allowlists metadata, generates embeddings, indexes to Qdrant.

Block B implementation:
- Metadata allowlisting via registry
- Embedding generation via embedding service
- Vector storage via Qdrant

The indexer NEVER imports specific connectors by name.
"""

from typing import List, Optional
import logging

from app.core.base_connector import UnifiedDocument
from app.services.registry import connector_registry
from app.services.embedding import embedding_service
from app.storage.qdrant_client import qdrant_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class Indexer:
    """
    Blind indexer implementation.
    
    Pipeline:
    1. Allowlist metadata fields per source_type (via registry/manifest)
    2. Generate embeddings for document content
    3. Index to Qdrant with vectors
    4. Handle deletions
    """

    def __init__(self):
        """Initialize indexer with dependencies."""
        self.registry = connector_registry
        self.embedding_service = embedding_service
        self.qdrant = qdrant_client
        
        # Ensure Qdrant collection exists
        try:
            dimension = self.embedding_service.get_dimension()
            self.qdrant.ensure_collection(dimension)
        except Exception as e:
            logger.warning(f"Could not initialize Qdrant collection: {e}")

    async def bulk_index(
        self,
        documents: List[UnifiedDocument],
        tenant_id: str,
        extra_acl: Optional[List[str]] = None,
    ) -> None:
        """
        Index a batch of documents.
        
        Args:
            documents: List of UnifiedDocument instances
            tenant_id: Tenant UUID
        """
        if not documents:
            return
        
        logger.info(f"Indexing {len(documents)} documents for tenant {tenant_id}")
        
        # Allowlist metadata per source_type
        processed_docs = []
        for doc in documents:
            allowed_keys = self.registry.get_allowed_metadata_keys(doc.source_type)
            
            # Filter metadata to allowed keys only
            filtered_metadata = {
                k: v for k, v in doc.structured_metadata.items()
                if k in allowed_keys
            }
            
            full_content = doc.content or ""
            owner_acl = list(extra_acl or [])
            doc_dict = {
                "id": doc.id,
                "title": doc.title,
                "content": full_content,
                "source_type": doc.source_type,
                "url": doc.url,
                "permissions": owner_acl or list(doc.permissions),
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
                "source_updated_at": doc.source_updated_at.isoformat(),
                "structured_metadata": filtered_metadata,
                "tenant_id": tenant_id,  # Add tenant_id for filtering
            }
            processed_docs.append(doc_dict)
        
        # Generate embeddings (cap text length for speed / provider limits)
        texts = [
            f"{doc['title']} {doc['content']}"[:12000] for doc in processed_docs
        ]
        vectors = await self.embedding_service.embed_texts(texts)

        # Block B Qdrant payloads: truncate bodies so large Gmail batches don't timeout
        qdrant_docs = []
        for doc in processed_docs:
            payload = dict(doc)
            body = payload.get("content") or ""
            if len(body) > 8000:
                payload["content"] = body[:8000]
            qdrant_docs.append(payload)

        await self.qdrant.upsert_documents(qdrant_docs, vectors)

        await self._fanout_search_pipeline(processed_docs, vectors, tenant_id, extra_acl or [])
        
        logger.info(f"Successfully indexed {len(documents)} documents for tenant {tenant_id}")

    async def _fanout_search_pipeline(
        self,
        processed_docs: List[dict],
        vectors: List[List[float]],
        tenant_id: str,
        extra_acl: List[str],
    ) -> None:
        """Write Block E chunks + F lexical + G vector + K document store + local index."""
        from app.services.ingest.local_index import local_ingest_index
        from app.services.chunking.prose import ProseChunker

        chunker = ProseChunker()
        model_version = (
            getattr(settings, "embedding_model_version", None)
            or getattr(settings, "model_version", None)
            or "default"
        )
        lexical_docs = []
        vector_chunks = []

        for doc, vector in zip(processed_docs, vectors):
            doc_id = str(doc["id"])
            acl_terms = (
                _acl_terms(extra_acl, None)
                if extra_acl
                else _acl_terms(doc.get("permissions") or [], extra_acl)
            )
            body = doc.get("content") or ""
            title = doc.get("title") or ""
            local_ingest_index.upsert(
                tenant_id,
                {
                    "document_id": doc_id,
                    "title": title,
                    "body_text": body,
                    "content": body,
                    "acl_terms": acl_terms,
                    "source": doc.get("source_type"),
                },
            )
            lexical_docs.append(
                {
                    "document_id": doc_id,
                    "title": title,
                    "body_text": body,
                    "source": doc.get("source_type"),
                    "acl_filter_terms": acl_terms,
                    "deleted": False,
                }
            )
            pieces = chunker.chunk(f"{title}\n{body}") or [
                {"id": "0", "content": f"{title}\n{body}"[:2000]}
            ]
            for piece in pieces:
                vector_chunks.append(
                    {
                        "chunk_id": f"{doc_id}:{piece.get('id') or '0'}",
                        "document_id": doc_id,
                        "embedding": vector,
                        "model_version": str(model_version),
                        "acl_terms": acl_terms,
                        "chunk_text": piece.get("content") or "",
                        "metadata": {"source_type": doc.get("source_type"), "title": title},
                    }
                )
            try:
                from app.services.document_reader.store import get_shared_document_store

                store = get_shared_document_store()
                if hasattr(store, "upsert"):
                    await store.upsert(
                        tenant_id,
                        doc_id,
                        title=title,
                        body=body,
                        structured_metadata=doc.get("structured_metadata") or {},
                        owner_principal_id=next(
                            (p.split(":", 1)[-1] for p in acl_terms if ":" in str(p)),
                            "",
                        ),
                        created_at=doc.get("created_at"),
                        updated_at=doc.get("updated_at"),
                        acl_entries=acl_terms,
                    )
            except Exception:
                logger.warning("document store upsert failed id=%s", doc_id, exc_info=True)

        try:
            from app.services.lexical.opensearch_store import OpenSearchLexicalStore

            await OpenSearchLexicalStore().index_batch(tenant_id, lexical_docs)
        except Exception:
            logger.warning("lexical index fan-out skipped", exc_info=True)

        try:
            from app.services.vector.qdrant_store import QdrantVectorStore

            await QdrantVectorStore().upsert_batch(tenant_id, vector_chunks)
        except Exception:
            logger.warning("vector index fan-out skipped", exc_info=True)

    async def delete_by_ids(
        self,
        document_ids: List[str],
        tenant_id: str,
        source_type: str,
    ) -> None:
        """
        Delete documents by ID.
        
        Args:
            document_ids: List of document IDs to delete
            tenant_id: Tenant UUID
            source_type: Source type
        """
        if not document_ids:
            return
        
        logger.info(
            f"Deleting {len(document_ids)} documents from {source_type} for tenant {tenant_id}"
        )
        
        await self.qdrant.delete_by_ids(document_ids, tenant_id=tenant_id)
        await self._delete_canonical_acls(document_ids, tenant_id)

    async def _delete_canonical_acls(
        self,
        document_ids: List[str],
        tenant_id: str,
    ) -> None:
        """Drop matching canonical_documents and acl_entries (fail closed on routing)."""
        from uuid import UUID

        from app.core.exceptions import TenantNotFoundError
        from app.services.tenant_resolver import tenant_resolver
        from app.storage.canonical_repo import CanonicalRepo
        from app.storage.tenant_db import tenant_db_manager

        try:
            tenant_uuid = UUID(str(tenant_id))
        except (TypeError, ValueError):
            logger.error("delete ACL skipped: invalid tenant_id")
            return

        try:
            routing = await tenant_resolver.resolve(str(tenant_id))
        except TenantNotFoundError:
            logger.error("delete ACL tenant not found tenant_id=%s", tenant_id)
            return
        except Exception:
            logger.exception("delete ACL routing failed tenant_id=%s", tenant_id)
            raise

        async for session in tenant_db_manager.get_session(
            routing.db_host,
            routing.db_name,
            routing.db_user,
            routing.db_password,
            str(routing.tenant_id),
        ):
            repo = CanonicalRepo(use_memory=False, session=session)
            await repo.delete_documents_and_acls(document_ids, tenant_uuid)
            return
        
    async def reindex_by_ids(
        self,
        tenant_id: str,
        document_ids: List[str],
        repo,
    ) -> None:
        """Rebuild UnifiedDocuments for ``document_ids`` and call ``bulk_index``.

        ``bulk_index`` cannot accept an id list; this is the minimal scoped wrapper.
        """
        if not document_ids:
            return
        from app.core.base_connector import UnifiedDocument

        documents = []
        for document_id in document_ids:
            doc = await repo.get_document(document_id)
            if doc is None:
                logger.warning("reindex skipped missing document_id=%s", document_id)
                continue
            entries = await repo.get_acl_entries(document_id)
            permissions = []
            for entry in entries:
                if entry.principal_id:
                    permissions.append(f"user:{entry.principal_id}")
                elif entry.group_id:
                    permissions.append(f"group:{entry.group_id}")
            documents.append(
                UnifiedDocument(
                    id=doc.source_id,
                    title=doc.title,
                    content=doc.content,
                    source_type=doc.source_type,
                    url=doc.url,
                    permissions=list(set(permissions)),
                    created_at=doc.created_at,
                    updated_at=doc.updated_at,
                    source_updated_at=doc.source_updated_at,
                    structured_metadata=doc.structured_metadata or {},
                )
            )
        if documents:
            await self.bulk_index(documents, tenant_id)


# Global indexer instance
indexer = Indexer()


def _acl_terms(permissions: List[str], extra_acl: Optional[List[str]] = None) -> List[str]:
    terms = []
    seen = set()
    for raw in list(permissions or []) + list(extra_acl or []):
        value = str(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        terms.append(value)
        if value.startswith("user:") or value.startswith("group:"):
            bare = value.split(":", 1)[-1]
            if bare and bare not in seen:
                seen.add(bare)
                terms.append(bare)
    return terms
