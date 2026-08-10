"""Shared pytest fixtures for Block G signoff tests."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest
import pytest_asyncio

# Ensure app imports resolve
ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("VECTOR_DB_TYPE", os.environ.get("VECTOR_DB_TYPE", "mock"))
os.environ.setdefault("EMBEDDING_DIMENSIONS", "64")
os.environ.setdefault("ENFORCE_TENANT_ISOLATION", "true")

FIXTURES = ROOT / "fixtures"


def _load_json(name: str) -> Dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_bearer(tenant_id: str, principal_id: str = "user:alice") -> str:
    """Build an unverified JWT-shaped bearer for tests."""
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "principal_id": principal_id,
                "scopes": ["search.vector", "ingest.vector"],
            }
        ).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.testsig"


@pytest.fixture(scope="session")
def corpus() -> Dict[str, Any]:
    return _load_json("corpus_chunks.json")


@pytest.fixture(scope="session")
def relevance() -> Dict[str, Any]:
    return _load_json("relevance_labels.json")


@pytest.fixture(scope="session")
def redteam() -> Dict[str, Any]:
    return _load_json("acl_redteam_cases.json")


@pytest.fixture(scope="session")
def db_type() -> str:
    return os.environ.get("VECTOR_DB_TYPE", "mock").lower()


@pytest_asyncio.fixture
async def loaded_store(corpus, db_type):
    """Fresh store pre-loaded with corpus (v1 embeddings)."""
    from app.services.factory import get_vector_store, reset_mock_store
    from app.services.mock_store import MockVectorStore
    from app.services.qdrant_store import QdrantVectorStore

    tenant_id = corpus["tenant_id"]
    dims = corpus["dimensions"]

    if db_type == "qdrant":
        store = QdrantVectorStore(dimensions=dims)
        await store.clear_tenant(tenant_id)
        await store.ensure_tenant(tenant_id, dims)
    else:
        store = reset_mock_store()
        await store.clear_tenant(tenant_id)
        await store.ensure_tenant(tenant_id, dims)

    for chunk in corpus["chunks"]:
        await store.upsert_chunk(
            tenant_id=chunk["tenant_id"],
            chunk_id=chunk["chunk_id"],
            embedding=chunk["embedding"],
            metadata={
                "document_id": chunk["document_id"],
                "chunk_text": chunk["chunk_text"],
                "metadata": chunk.get("metadata") or {},
            },
            acl_terms=chunk["acl_filter_terms"],
            model_version=chunk["model_version"],
        )
    return store


@pytest_asyncio.fixture
async def mixed_version_store(corpus, db_type):
    """Store with both model versions for the same public chunks."""
    from app.services.factory import reset_mock_store
    from app.services.qdrant_store import QdrantVectorStore

    tenant_id = corpus["tenant_id"]
    dims = corpus["dimensions"]
    v1, v2 = corpus["model_versions"]

    if db_type == "qdrant":
        store = QdrantVectorStore(dimensions=dims)
        await store.clear_tenant(tenant_id)
        await store.ensure_tenant(tenant_id, dims)
    else:
        store = reset_mock_store()
        await store.clear_tenant(tenant_id)
        await store.ensure_tenant(tenant_id, dims)

    for chunk in corpus["chunks"]:
        await store.upsert_chunk(
            tenant_id=chunk["tenant_id"],
            chunk_id=chunk["chunk_id"],
            embedding=chunk["embedding"],
            metadata={
                "document_id": chunk["document_id"],
                "chunk_text": chunk["chunk_text"],
                "metadata": chunk.get("metadata") or {},
            },
            acl_terms=chunk["acl_filter_terms"],
            model_version=v1,
        )
        if chunk["chunk_id"].startswith("chunk-public-"):
            await store.upsert_chunk(
                tenant_id=chunk["tenant_id"],
                chunk_id=chunk["chunk_id"],
                embedding=chunk["embedding_v2"],
                metadata={
                    "document_id": chunk["document_id"],
                    "chunk_text": chunk["chunk_text"] + " [v2]",
                    "metadata": {**(chunk.get("metadata") or {}), "reembed": True},
                },
                acl_terms=chunk["acl_filter_terms"],
                model_version=v2,
            )
    return store