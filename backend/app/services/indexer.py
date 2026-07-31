"""
Blind Indexer: accepts UnifiedDocument, allowlists metadata, generates embeddings, indexes to Qdrant.

Block B implementation:
- Metadata allowlisting via registry
- Embedding generation via embedding service
- Vector storage via Qdrant

The indexer NEVER imports specific connectors by name.
"""

from typing import List
import logging

from app.core.base_connector import UnifiedDocument
from app.services.registry import connector_registry
from app.services.embedding import embedding_service
from app.storage.qdrant_client import qdrant_client

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
            
            # Prepare document for indexing
            doc_dict = {
                "id": doc.id,
                "title": doc.title,
                "content": doc.content,
                "source_type": doc.source_type,
                "url": doc.url,
                "permissions": doc.permissions,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
                "source_updated_at": doc.source_updated_at.isoformat(),
                "structured_metadata": filtered_metadata,
                "tenant_id": tenant_id,  # Add tenant_id for filtering
            }
            processed_docs.append(doc_dict)
        
        # Generate embeddings
        texts = [f"{doc['title']} {doc['content']}" for doc in processed_docs]
        vectors = await self.embedding_service.embed_texts(texts)
        
        # Index to Qdrant
        await self.qdrant.upsert_documents(processed_docs, vectors)
        
        logger.info(f"Successfully indexed {len(documents)} documents for tenant {tenant_id}")

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
        
        # Delete from Qdrant
        await self.qdrant.delete_by_ids(document_ids)
        
        logger.info(
            f"Successfully deleted {len(document_ids)} documents for tenant {tenant_id}"
        )


# Global indexer instance
indexer = Indexer()
