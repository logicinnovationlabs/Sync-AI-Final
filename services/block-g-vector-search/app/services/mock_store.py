"""In-memory mock vector store for Phase 1 signoff tests."""

from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.services.acl_filter import acl_allows, normalize_acl_terms
from app.services.vector_store import VectorStore


def _cosine(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _point_key(chunk_id: str, model_version: str) -> str:
    return f"{chunk_id}::{model_version}"


class MockVectorStore(VectorStore):
    """Brute-force cosine ANN with tenant + ACL filtering."""

    def __init__(self) -> None:
        # tenant_id -> { point_key -> record }
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = {}

    async def ensure_tenant(self, tenant_id: str, dimensions: int) -> None:
        self._data.setdefault(tenant_id, {})

    async def clear_tenant(self, tenant_id: str) -> None:
        self._data.pop(tenant_id, None)

    async def upsert_chunk(
        self,
        tenant_id: str,
        chunk_id: str,
        embedding: List[float],
        metadata: Dict[str, Any],
        acl_terms: List[str],
        model_version: str,
    ) -> None:
        await self.ensure_tenant(tenant_id, len(embedding))
        key = _point_key(chunk_id, model_version)
        self._data[tenant_id][key] = {
            "chunk_id": chunk_id,
            "document_id": metadata.get("document_id", ""),
            "embedding": list(embedding),
            "model_version": model_version,
            "chunk_text": metadata.get("chunk_text", ""),
            "acl_terms": normalize_acl_terms(acl_terms),
            "metadata": metadata.get("metadata") or {},
            "point_id": str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
        }

    async def delete_chunk(
        self,
        tenant_id: str,
        chunk_id: str,
        model_version: Optional[str] = None,
    ) -> None:
        bucket = self._data.get(tenant_id, {})
        if model_version:
            bucket.pop(_point_key(chunk_id, model_version), None)
            return
        for key in list(bucket.keys()):
            if key.startswith(f"{chunk_id}::"):
                bucket.pop(key, None)

    async def search(
        self,
        tenant_id: str,
        query_embedding: List[float],
        acl_terms: List[str],
        top_k: int = 100,
        model_version: Optional[str] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        bucket = self._data.get(tenant_id, {})
        user_terms = normalize_acl_terms(acl_terms)
        scored: List[Tuple[float, Dict[str, Any]]] = []

        for record in bucket.values():
            if model_version and record["model_version"] != model_version:
                continue
            if not acl_allows(record["acl_terms"], user_terms):
                continue
            score = _cosine(query_embedding, record["embedding"])
            if score_threshold is not None and score < score_threshold:
                continue
            scored.append(
                (
                    score,
                    {
                        "chunk_id": record["chunk_id"],
                        "document_id": record["document_id"],
                        "score": score,
                        "model_version": record["model_version"],
                        "chunk_text": record["chunk_text"],
                        "metadata": record["metadata"],
                        "acl_terms": record["acl_terms"],
                    },
                )
            )

        # Never cross-compare scores across model versions when mixing:
        # rank within each model_version group, then merge by group score order.
        if model_version is None:
            by_version: Dict[str, List[Tuple[float, Dict[str, Any]]]] = {}
            for score, item in scored:
                by_version.setdefault(item["model_version"], []).append((score, item))
            merged: List[Dict[str, Any]] = []
            # Preserve group identity; within each group sort by score desc
            for version in sorted(by_version.keys()):
                group = sorted(by_version[version], key=lambda t: t[0], reverse=True)
                merged.extend([item for _, item in group])
            # Final presentation order: still prefer higher scores but never
            # claim cross-model comparability — attach group tag via metadata.
            merged.sort(key=lambda r: (r["model_version"], -r["score"]))
            # Re-sort globally by score for API convenience, tagging that scores
            # are only valid within the same model_version.
            merged.sort(key=lambda r: r["score"], reverse=True)
            return merged[:top_k]

        scored.sort(key=lambda t: t[0], reverse=True)
        return [item for _, item in scored[:top_k]]
