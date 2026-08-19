"""
Qdrant client wrapper - vector database operations.

Provides:
- Collection management (create, delete)
- Document indexing (upsert with vectors)
- Document deletion
- Search (similarity search with filters)
"""

from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient as QdrantClientSDK
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    HasIdCondition,
)
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


import uuid

def _to_qdrant_id(raw_id: Any) -> str:
    """
    Convert any document ID to a valid Qdrant point ID.
    Qdrant requires point IDs to be an unsigned integer or a valid UUID string.
    """
    raw_str = str(raw_id)
    if raw_str.isdigit():
        return int(raw_str)
    try:
        uuid.UUID(raw_str)
        return raw_str
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, raw_str))


class QdrantClient:
    """
    Qdrant client wrapper.
    
    Manages vector storage and retrieval for document embeddings.
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        """
        Initialize Qdrant client.
        
        Args:
            url: Qdrant URL (defaults to settings.QDRANT_URL)
            api_key: Qdrant API key (optional)
            collection_name: Collection name (defaults to settings.QDRANT_COLLECTION_NAME)
        """
        self.url = (
            url
            or getattr(settings, "qdrant_url", None)
            or getattr(settings, "QDRANT_URL", "http://localhost:6333")
        )
        self.api_key = (
            api_key
            or getattr(settings, "qdrant_api_key", None)
            or getattr(settings, "QDRANT_API_KEY", None)
        )
        self.collection_name = (
            collection_name
            or getattr(settings, "qdrant_collection_name", None)
            or getattr(settings, "QDRANT_COLLECTION_NAME", "documents")
        )
        
        # Initialize SDK client
        self.client = QdrantClientSDK(
            url=self.url,
            api_key=self.api_key,
        )
    
    def create_collection(
        self,
        dimension: int,
        distance: Distance = Distance.COSINE,
    ) -> None:
        """
        Create a collection with specified vector dimension.
        
        Args:
            dimension: Vector dimension (e.g., 768 for Gemini)
            distance: Distance metric (COSINE, EUCLID, DOT)
        """
        try:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=dimension, distance=distance),
            )
            logger.info(f"Created Qdrant collection: {self.collection_name}")
        except Exception as e:
            # Collection may already exist
            logger.warning(f"Could not create collection {self.collection_name}: {e}")
    
    def collection_exists(self) -> bool:
        """
        Check if collection exists.
        
        Returns:
            True if collection exists
        """
        try:
            collections = self.client.get_collections().collections
            return any(c.name == self.collection_name for c in collections)
        except Exception:
            return False
    
    def ensure_collection(self, dimension: int) -> None:
        """
        Ensure collection exists, create if not.
        
        Args:
            dimension: Vector dimension
        """
        try:
            if not self.collection_exists():
                self.create_collection(dimension)
        except Exception as e:
            logger.warning(f"Could not connect to or ensure Qdrant collection: {e}")
    
    async def upsert_documents(
        self,
        documents: List[Dict[str, Any]],
        vectors: List[List[float]],
    ) -> None:
        """
        Upsert documents with their embeddings.
        
        Args:
            documents: List of document dicts (must have 'id' field)
            vectors: List of embedding vectors (parallel to documents)
        """
        if len(documents) != len(vectors):
            raise ValueError("Documents and vectors must have same length")
        
        if not documents:
            return
        
        # Convert to Qdrant points
        points = []
        for doc, vector in zip(documents, vectors):
            doc_id = doc.get("id")
            if not doc_id:
                logger.warning("Skipping document without ID")
                continue
            
            point = PointStruct(
                id=_to_qdrant_id(doc_id),
                vector=vector,
                payload=doc,
            )
            points.append(point)
        
        # Upsert to Qdrant
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            logger.info(f"Upserted {len(points)} documents to Qdrant")
        except Exception as e:
            logger.error(f"Failed to upsert documents to Qdrant: {e}")
            raise
    
    async def delete_by_ids(
        self,
        ids: List[str],
        tenant_id: str,
    ) -> None:
        """
        Delete documents by IDs, scoped to a tenant payload filter.

        Args:
            ids: List of document IDs to delete
            tenant_id: Tenant UUID — required so a colliding ID cannot
                delete another tenant's points.
        """
        if not ids:
            return
        if not tenant_id:
            raise ValueError("tenant_id is required for vector deletes")

        qdrant_ids = [_to_qdrant_id(i) for i in ids]
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="tenant_id",
                            match=MatchValue(value=str(tenant_id)),
                        ),
                        HasIdCondition(has_id=qdrant_ids),
                    ]
                ),
            )
            logger.info(
                "Deleted %s documents from Qdrant for tenant %s",
                len(ids),
                tenant_id,
            )
        except Exception as e:
            logger.error("Failed to delete documents from Qdrant: %s", e)
            raise
    
    async def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Similarity search with optional filters.
        
        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results
            filters: Optional filter dict (e.g., {"tenant_id": "abc", "source_type": "google_drive"})
            
        Returns:
            List of matched documents with scores
        """
        # Build Qdrant filter
        qdrant_filter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                conditions.append(
                    FieldCondition(key=key, match=MatchValue(value=value))
                )
            if conditions:
                qdrant_filter = Filter(must=conditions)
        
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                query_filter=qdrant_filter,
            )
            
            # Convert to dicts
            documents = []
            for result in results:
                doc = result.payload
                doc["_score"] = result.score
                documents.append(doc)
            
            return documents
        
        except Exception as e:
            logger.error(f"Failed to search Qdrant: {e}")
            raise
    
    def delete_collection(self) -> None:
        """Delete the collection."""
        try:
            self.client.delete_collection(self.collection_name)
            logger.info(f"Deleted Qdrant collection: {self.collection_name}")
        except Exception as e:
            logger.warning(f"Could not delete collection {self.collection_name}: {e}")


# Global Qdrant client instance
qdrant_client = QdrantClient()
