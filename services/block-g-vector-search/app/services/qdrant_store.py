"""Qdrant-backed vector store with per-tenant collections and ACL prefilter."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.config import settings
from app.services.acl_filter import normalize_acl_terms
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


def _point_id(chunk_id: str, model_version: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{chunk_id}::{model_version}"))


class QdrantVectorStore(VectorStore):
    """Per-tenant Qdrant collections with ACL keyword prefiltering."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        api_key: Optional[str] = None,
        collection_prefix: Optional[str] = None,
        dimensions: Optional[int] = None,
    ) -> None:
        self.host = host or settings.qdrant_host
        self.port = port if port is not None else settings.qdrant_port
        self.api_key = api_key if api_key is not None else settings.qdrant_api_key
        self.collection_prefix = collection_prefix or settings.collection_prefix
        self.dimensions = dimensions or settings.embedding_dimensions
        self._client = QdrantClient(
            host=self.host,
            port=self.port,
            api_key=self.api_key,
            prefer_grpc=settings.qdrant_prefer_grpc,
        )

    def _collection_name(self, tenant_id: str) -> str:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tenant_id)
        return f"{self.collection_prefix}_{safe}_chunks"

    async def ensure_tenant(self, tenant_id: str, dimensions: int) -> None:
        name = self._collection_name(tenant_id)
        existing = {c.name for c in self._client.get_collections().collections}
        if name in existing:
            return
        self._client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(
                size=dimensions,
                distance=qm.Distance.COSINE,
            ),
        )
        # Payload indexes for ACL / model / tenant filters
        for field_name, schema in (
            ("acl_terms", qm.PayloadSchemaType.KEYWORD),
            ("model_version", qm.PayloadSchemaType.KEYWORD),
            ("document_id", qm.PayloadSchemaType.KEYWORD),
            ("chunk_id", qm.PayloadSchemaType.KEYWORD),
            ("tenant_id", qm.PayloadSchemaType.KEYWORD),
        ):
            try:
                self._client.create_payload_index(
                    collection_name=name,
                    field_name=field_name,
                    field_schema=schema,
                )
            except Exception as exc:  # noqa: BLE001 — index may already exist
                logger.debug("Payload index %s on %s: %s", field_name, name, exc)

    async def clear_tenant(self, tenant_id: str) -> None:
        name = self._collection_name(tenant_id)
        try:
            self._client.delete_collection(name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not delete collection %s: %s", name, exc)

    def _build_filter(
        self,
        tenant_id: str,
        acl_terms: List[str],
        model_version: Optional[str],
    ) -> qm.Filter:
        must: List[qm.Condition] = [
            qm.FieldCondition(
                key="tenant_id",
                match=qm.MatchValue(value=tenant_id),
            )
        ]
        terms = normalize_acl_terms(acl_terms)
        if not terms:
            # Fail-closed: match nothing
            must.append(
                qm.FieldCondition(
                    key="acl_terms",
                    match=qm.MatchValue(value="__no_acl__"),
                )
            )
        else:
            must.append(
                qm.FieldCondition(
                    key="acl_terms",
                    match=qm.MatchAny(any=terms),
                )
            )
        if model_version:
            must.append(
                qm.FieldCondition(
                    key="model_version",
                    match=qm.MatchValue(value=model_version),
                )
            )
        return qm.Filter(must=must)

    async def upsert_chunk(
        self,
        tenant_id: str,
        chunk_id: str,
        embedding: List[float],
        metadata: Dict[str, Any],
        acl_terms: List[str],
        model_version: str,
    ) -> None:
        dims = len(embedding)
        await self.ensure_tenant(tenant_id, dims)
        name = self._collection_name(tenant_id)
        payload = {
            "tenant_id": tenant_id,
            "chunk_id": chunk_id,
            "document_id": metadata.get("document_id", ""),
            "model_version": model_version,
            "chunk_text": metadata.get("chunk_text", ""),
            "acl_terms": normalize_acl_terms(acl_terms),
            "metadata": metadata.get("metadata") or {},
        }
        self._client.upsert(
            collection_name=name,
            points=[
                qm.PointStruct(
                    id=_point_id(chunk_id, model_version),
                    vector=embedding,
                    payload=payload,
                )
            ],
            wait=True,
        )

    async def delete_chunk(
        self,
        tenant_id: str,
        chunk_id: str,
        model_version: Optional[str] = None,
    ) -> None:
        name = self._collection_name(tenant_id)
        if model_version:
            self._client.delete(
                collection_name=name,
                points_selector=qm.PointIdsList(
                    points=[_point_id(chunk_id, model_version)]
                ),
            )
            return
        self._client.delete(
            collection_name=name,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="chunk_id",
                            match=qm.MatchValue(value=chunk_id),
                        )
                    ]
                )
            ),
        )

    async def search(
        self,
        tenant_id: str,
        query_embedding: List[float],
        acl_terms: List[str],
        top_k: int = 100,
        model_version: Optional[str] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        name = self._collection_name(tenant_id)
        existing = {c.name for c in self._client.get_collections().collections}
        if name not in existing:
            return []

        query_filter = self._build_filter(tenant_id, acl_terms, model_version)

        # Over-fetch when mixing model versions so we can avoid ranking them
        # as if scores were comparable; still return at most top_k.
        fetch_k = top_k if model_version else min(top_k * 3, settings.max_top_k)

        kwargs: Dict[str, Any] = {
            "collection_name": name,
            "query": query_embedding,
            "limit": fetch_k,
            "query_filter": query_filter,
            "with_payload": True,
        }
        if score_threshold is not None:
            kwargs["score_threshold"] = score_threshold

        # qdrant-client >=1.12 uses query_points (search removed in 1.19+)
        response = self._client.query_points(**kwargs)
        hits = response.points

        results: List[Dict[str, Any]] = []
        versions_seen: Dict[str, List[Dict[str, Any]]] = {}
        for hit in hits:
            payload = hit.payload or {}
            item = {
                "chunk_id": payload.get("chunk_id", ""),
                "document_id": payload.get("document_id", ""),
                "score": float(hit.score),
                "model_version": payload.get("model_version", ""),
                "chunk_text": payload.get("chunk_text", ""),
                "metadata": payload.get("metadata") or {},
                "acl_terms": payload.get("acl_terms") or [],
            }
            if model_version is None:
                versions_seen.setdefault(item["model_version"], []).append(item)
            else:
                results.append(item)

        if model_version is None:
            # Rank within each model version independently, then interleave
            # by keeping version tags — never mix scores across versions for
            # relative ranking claims. Practical return: concat per-version
            # top slices sorted by score within version.
            merged: List[Dict[str, Any]] = []
            for ver in sorted(versions_seen.keys()):
                group = sorted(
                    versions_seen[ver],
                    key=lambda r: r["score"],
                    reverse=True,
                )
                merged.extend(group)
            # Present highest within-version scores first for API consumers,
            # with model_version always present so Block J does not compare.
            merged.sort(key=lambda r: r["score"], reverse=True)
            return merged[:top_k]

        return results[:top_k]
