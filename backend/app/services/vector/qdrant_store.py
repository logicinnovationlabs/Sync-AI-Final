"""
Qdrant-backed vector store for production semantic search.
Implements per-tenant collections with ACL prefiltering and model version isolation.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.services.rag_debug_trace import get_tracer as _get_rag_tracer

from opentelemetry import trace

from app.core.config import settings
from app.acl.filter import (
    document_is_visible,
    is_bypass,
    is_fail_closed,
    qdrant_must_not_acl,
)
from app.services.vector.store import VectorStore

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)


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
        
        from app.storage.vault_client import PlatformSecretKeys, vault_client

        qdrant_url = getattr(settings, "qdrant_url", None)
        api_key = vault_client.get(PlatformSecretKeys.QDRANT_API_KEY) or None
        if api_key in ("", "mock-secret"):
            api_key = None
        if qdrant_url:
            self._client = QdrantClient(url=qdrant_url, api_key=api_key, timeout=120)
        else:
            host = getattr(settings, "qdrant_host", "localhost")
            port = getattr(settings, "qdrant_port", 6333)
            self._client = QdrantClient(host=host, port=port, api_key=api_key, timeout=120)
        
        self.collection_prefix = getattr(settings, 'qdrant_collection_prefix', 'snyq')
        # Prefer explicit EMBEDDING_DIMENSIONS; fall back to EMBEDDING_DIMENSION
        # so fake/local embeds and the vector collection stay aligned.
        self.dimensions = int(
            getattr(settings, "embedding_dimensions", None)
            or getattr(settings, "embedding_dimension", None)
            or 3072
        )
        self._upsert_batch_size = 16
        self._ensured_collections: set[str] = set()
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
        if name in self._ensured_collections:
            return
        
        try:
            collection_info = self._client.get_collection(collection_name=name)
            # Check dimensions if vectors configuration is present
            vectors_cfg = getattr(getattr(collection_info, "config", None), "params", None)
            vectors_obj = getattr(vectors_cfg, "vectors", None)
            vector_size = getattr(vectors_obj, "size", None)
            if vector_size is not None and vector_size != self.dimensions:
                logger.warning(f"Collection {name} has wrong dimensions ({vector_size} != {self.dimensions}), deleting and recreating...")
                self._client.delete_collection(collection_name=name)
            else:
                self._ensured_collections.add(name)
                return  # Collection exists with correct dimensions
        except Exception as e:
            # Collection doesn't exist or check failed - attempt creation
            logger.debug(f"Collection check on {name}: {e}")
        
        # Create collection
        try:
            self._client.create_collection(
                collection_name=name,
                vectors_config=self.qm.VectorParams(
                    size=self.dimensions,
                    distance=self.qm.Distance.COSINE,
                ),
            )
        except Exception as e:
            # If already exists (409 Conflict), ignore
            if "already exists" in str(e).lower() or "conflict" in str(e).lower() or "409" in str(e):
                logger.debug(f"Collection {name} already created")
            else:
                raise e
        
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
        
        self._ensured_collections.add(name)
        logger.info(f"Created/verified Qdrant collection: {name} with dimensions {self.dimensions}")

    
    async def search(
        self,
        tenant_id: str,
        query_embedding: List[float],
        acl_terms: List[str],
        top_k: int = 10,
        model_version: Optional[str] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Execute ANN search with ACL prefilter (allow + explicit deny)."""
        with _tracer.start_as_current_span("qdrant.query") as span:
            span.set_attribute("db.system", "qdrant")
            span.set_attribute("db.operation", "search")
            span.set_attribute("tenant.id", tenant_id)

            # Fail-closed
            if is_fail_closed(acl_terms):
                return []

            self._ensure_collection(tenant_id)
            name = self._collection_name(tenant_id)

            normalized_query = self._normalize_embedding(query_embedding)

            must_conditions = [
                self.qm.FieldCondition(
                    key="tenant_id",
                    match=self.qm.MatchValue(value=tenant_id),
                )
            ]

            if not is_bypass(acl_terms):
                must_conditions.append(
                    self.qm.FieldCondition(
                        key="acl_terms",
                        match=self.qm.MatchAny(any=list(acl_terms)),
                    )
                )

            if model_version:
                must_conditions.append(
                    self.qm.FieldCondition(
                        key="model_version",
                        match=self.qm.MatchValue(value=model_version),
                    )
                )

            must_not = []
            deny_cond = qdrant_must_not_acl(self.qm, acl_terms) if not is_bypass(acl_terms) else None
            if deny_cond is not None:
                must_not.append(deny_cond)

            filter_kwargs = {"must": must_conditions}
            if must_not:
                filter_kwargs["must_not"] = must_not
            filter_obj = self.qm.Filter(**filter_kwargs)

            try:
                self._ensure_collection(tenant_id)
                results = self._client.search(
                    collection_name=name,
                    query_vector=normalized_query,
                    query_filter=filter_obj,
                    limit=fetch_k,
                    score_threshold=score_threshold,
                )
            except Exception as e:
                span.set_attribute("error", True)
                logger.warning(f"Qdrant search failed: {e}")
                return []

            # --- Rule #2, Stage 5: vector retrieval BEFORE ACL post-filter ---
            tracer = _get_rag_tracer()
            pre_acl_results = [
                {
                    "chunk_id": (hit.payload or {}).get("chunk_id", ""),
                    "document_id": (hit.payload or {}).get("document_id", ""),
                    "score": hit.score,
                    "title": ((hit.payload or {}).get("metadata") or {}).get("title", ""),
                }
                for hit in results
            ]
            tracer.log_vector_retrieval(pre_acl_results, pre_acl=True)
            pre_filter_count = len(results)

            output = []
            for hit in results:
                payload = hit.payload or {}
                if not document_is_visible(acl_terms, payload.get("acl_terms") or []):
                    continue
                output.append({
                    "chunk_id": payload.get("chunk_id", ""),
                    "document_id": payload.get("document_id", ""),
                    "score": hit.score,
                    "model_version": payload.get("model_version", ""),
                    "chunk_text": payload.get("chunk_text", ""),
                    "metadata": payload.get("metadata"),
                })
                if len(output) >= top_k:
                    break

            # --- Rule #2, Stage 6: ACL/tenant filter counts ---
            must_clause_repr = {
                "tenant_id": tenant_id,
                "acl_terms": list(acl_terms)[:10],
                "is_bypass": is_bypass(acl_terms),
            }
            tracer.log_acl_filter(must_clause_repr, pre_filter_count, len(output))

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
            chunk_text = chunk.get("chunk_text", "") or ""
            if len(chunk_text) > 4000:
                chunk_text = chunk_text[:4000]
            
            point = self.qm.PointStruct(
                id=_point_id(chunk["chunk_id"], chunk["model_version"]),
                vector=normalized_embedding,
                payload={
                    "tenant_id": tenant_id,
                    "chunk_id": chunk["chunk_id"],
                    "document_id": chunk["document_id"],
                    "model_version": chunk["model_version"],
                    "acl_terms": chunk.get("acl_terms", []),
                    "chunk_text": chunk_text,
                    "metadata": chunk.get("metadata", {}),
                },
            )
            points.append(point)
        
        batch = max(1, int(self._upsert_batch_size))
        for i in range(0, len(points), batch):
            self._client.upsert(
                collection_name=name,
                points=points[i : i + batch],
                wait=True,
            )
        logger.info(f"Upserted {len(points)} chunks to {name}")
        
        return len(points)

    def find_parent_document_id(
        self, tenant_id: str, chunk_or_doc_id: str
    ) -> Optional[str]:
        """Return the parent document_id for a chunk id, if this tenant has it.

        Does not create or recreate collections.
        """
        ident = str(chunk_or_doc_id or "").strip()
        if not ident or not tenant_id:
            return None
        name = self._collection_name(tenant_id)
        try:
            self._client.get_collection(collection_name=name)
        except Exception:
            return None
        for field in ("document_id", "chunk_id"):
            try:
                points, _ = self._client.scroll(
                    collection_name=name,
                    scroll_filter=self.qm.Filter(
                        must=[
                            self.qm.FieldCondition(
                                key=field,
                                match=self.qm.MatchValue(value=ident),
                            )
                        ]
                    ),
                    limit=1,
                    with_payload=True,
                    with_vectors=False,
                )
            except Exception as exc:
                logger.debug(
                    "chunk parent lookup %s=%s failed: %s", field, ident, exc
                )
                continue
            if not points:
                continue
            parent = str((points[0].payload or {}).get("document_id") or "").strip()
            if parent:
                return parent
        return None
    
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
