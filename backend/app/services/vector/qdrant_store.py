"""
Qdrant-backed vector store for production semantic search.
Implements per-tenant collections with ACL prefiltering and model version isolation.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.vector.store import VectorStore

logger = logging.getLogger(__name__)


def _point_id(chunk_id: str, model_version: str) -> str:
    """Generate deterministic Qdrant point ID."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{chunk_id}::{model_version}"))


class QdrantVectorStore(VectorStore):
    """Qdrant client with per-tenant collections and ACL prefiltering."""
    
    def __init__(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qm
            self.qm = qm
        except ImportError as exc:
            raise RuntimeError(
                "qdrant-client is required for Qdrant backend"
            ) from exc
        
        qdrant_url = getattr(settings, 'qdrant_url', None)
        if qdrant_url:
            self._client = QdrantClient(url=qdrant_url)
        else:
            host = getattr(settings, 'qdrant_host', 'localhost')
            port = getattr(settings, 'qdrant_port', 6333)
            self._client = QdrantClient(host=host, port=port)
        
        self.collection_prefix = getattr(settings, 'qdrant_collection_prefix', 'snyq')
        self.dimensions = settings.embedding_dimensions  # Use settings directly (default: 360)
        logger.info(f"QdrantVectorStore initialized with prefix: {self.collection_prefix}, dimensions: {self.dimensions}")
    
    def _normalize_embedding(self, embedding: List[float]) -> List[float]:
        """Normalize embedding to expected dimensions (pad with zeros or truncate)."""
        if len(embedding) == self.dimensions:
            return embedding
        elif len(embedding) < self.dimensions:
            # Pad with zeros
            logger.warning(f"Padding embedding from {len(embedding)} to {self.dimensions} dimensions")
            return embedding + [0.0] * (self.dimensions - len(embedding))
        else:
            # Truncate
            logger.warning(f"Truncating embedding from {len(embedding)} to {self.dimensions} dimensions")
            return embedding[:self.dimensions]
    
    def _collection_name(self, tenant_id: str) -> str:
        """Generate collection name for tenant."""
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tenant_id)
        return f"{self.collection_prefix}_{safe}_vectors"
    
    def _ensure_collection(self, tenant_id: str) -> None:
        """Ensure collection exists for tenant with correct dimensions."""
        name = self._collection_name(tenant_id)
        
        try:
            collection_info = self._client.get_collection(collection_name=name)
            # Check dimensions
            vector_size = collection_info.config.params.vectors.size
            if vector_size != self.dimensions:
                logger.warning(f"Collection {name} has wrong dimensions ({vector_size} != {self.dimensions}), deleting and recreating...")
                self._client.delete_collection(collection_name=name)
            else:
                return  # Collection exists with correct dimensions
        except Exception as e:
            # Collection doesn't exist or error - will create below
            logger.debug(f"Collection check failed: {e}")
        
        # Create collection
        self._client.create_collection(
            collection_name=name,
            vectors_config=self.qm.VectorParams(
                size=self.dimensions,
                distance=self.qm.Distance.COSINE,
            ),
        )
        
        # Create payload indexes for filtering
        for field_name in ["acl_terms", "model_version", "document_id", "chunk_id", "tenant_id"]:
            try:
                self._client.create_payload_index(
                    collection_name=name,
                    field_name=field_name,
                    field_schema=self.qm.PayloadSchemaType.KEYWORD,
                )
            except Exception as e:
                logger.debug(f"Payload index {field_name} on {name}: {e}")
        
        logger.info(f"Created Qdrant collection: {name} with dimensions {self.dimensions}")
    
    async def search(
        self,
        tenant_id: str,
        query_embedding: List[float],
        acl_terms: List[str],
        top_k: int = 10,
        model_version: Optional[str] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Execute ANN search with ACL prefilter."""
        self._ensure_collection(tenant_id)
        name = self._collection_name(tenant_id)
        
        # Normalize query embedding dimensions
        normalized_query = self._normalize_embedding(query_embedding)
        
        # Build filter
        must_conditions = [
            self.qm.FieldCondition(
                key="tenant_id",
                match=self.qm.MatchValue(value=tenant_id),
            )
        ]
        
        # ACL prefilter (fail-closed)
        if not acl_terms:
            return []
        
        must_conditions.append(
            self.qm.FieldCondition(
                key="acl_terms",
                match=self.qm.MatchAny(any=acl_terms),
            )
        )
        
        # Model version filter
        if model_version:
            must_conditions.append(
                self.qm.FieldCondition(
                    key="model_version",
                    match=self.qm.MatchValue(value=model_version),
                )
            )
        
        filter_obj = self.qm.Filter(must=must_conditions)
        
        # Execute search
        try:
            results = self._client.search(
                collection_name=name,
                query_vector=normalized_query,
                query_filter=filter_obj,
                limit=top_k,
                score_threshold=score_threshold,
            )
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            return []
        
        # Parse results
        output = []
        for hit in results:
            payload = hit.payload
            output.append({
                "chunk_id": payload.get("chunk_id", ""),
                "document_id": payload.get("document_id", ""),
                "score": hit.score,
                "model_version": payload.get("model_version", ""),
                "chunk_text": payload.get("chunk_text", ""),
                "metadata": payload.get("metadata"),
            })
        
        return output
    
    async def upsert_chunk(
        self,
        tenant_id: str,
        chunk_id: str,
        document_id: str,
        embedding: List[float],
        model_version: str,
        acl_terms: List[str],
        chunk_text: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Upsert a single chunk vector."""
        self._ensure_collection(tenant_id)
        name = self._collection_name(tenant_id)
        
        # Normalize embedding dimensions
        normalized_embedding = self._normalize_embedding(embedding)
        
        point = self.qm.PointStruct(
            id=_point_id(chunk_id, model_version),
            vector=normalized_embedding,
            payload={
                "tenant_id": tenant_id,
                "chunk_id": chunk_id,
                "document_id": document_id,
                "model_version": model_version,
                "acl_terms": acl_terms,
                "chunk_text": chunk_text,
                "metadata": metadata or {},
            },
        )
        
        self._client.upsert(collection_name=name, points=[point])
        logger.debug(f"Upserted chunk {chunk_id} to {name}")
    
    async def upsert_batch(
        self,
        tenant_id: str,
        chunks: List[Dict[str, Any]],
    ) -> int:
        """Bulk upsert chunk vectors."""
        if not chunks:
            return 0
        
        self._ensure_collection(tenant_id)
        name = self._collection_name(tenant_id)
        
        points = []
        for chunk in chunks:
            # Normalize embedding dimensions
            normalized_embedding = self._normalize_embedding(chunk["embedding"])
            
            point = self.qm.PointStruct(
                id=_point_id(chunk["chunk_id"], chunk["model_version"]),
                vector=normalized_embedding,
                payload={
                    "tenant_id": tenant_id,
                    "chunk_id": chunk["chunk_id"],
                    "document_id": chunk["document_id"],
                    "model_version": chunk["model_version"],
                    "acl_terms": chunk.get("acl_terms", []),
                    "chunk_text": chunk.get("chunk_text", ""),
                    "metadata": chunk.get("metadata", {}),
                },
            )
            points.append(point)
        
        self._client.upsert(collection_name=name, points=points)
        logger.info(f"Upserted {len(points)} chunks to {name}")
        
        return len(points)
    
    async def delete_chunk(
        self,
        tenant_id: str,
        chunk_id: str,
        model_version: str,
    ) -> None:
        """Delete a chunk vector."""
        name = self._collection_name(tenant_id)
        
        try:
            self._client.delete(
                collection_name=name,
                points_selector=self.qm.PointIdsList(
                    points=[_point_id(chunk_id, model_version)]
                ),
            )
            logger.debug(f"Deleted chunk {chunk_id} from {name}")
        except Exception as e:
            logger.warning(f"Failed to delete chunk {chunk_id}: {e}")
