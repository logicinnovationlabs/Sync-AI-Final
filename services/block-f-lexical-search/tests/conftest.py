"""Shared pytest fixtures for Block F signoff tests."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict

import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SEARCH_BACKEND", os.environ.get("SEARCH_BACKEND", "mock"))
os.environ.setdefault("ENFORCE_TENANT_ISOLATION", "true")

FIXTURES = ROOT / "fixtures"


def _load_json(name: str) -> Dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_bearer(tenant_id: str, principal_id: str = "user:alice") -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "principal_id": principal_id,
                "scopes": ["search.lexical", "ingest.lexical"],
            }
        ).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.testsig"


@pytest.fixture(scope="session")
def corpus() -> Dict[str, Any]:
    return _load_json("corpus_docs.json")


@pytest.fixture(scope="session")
def queries() -> Dict[str, Any]:
    return _load_json("representative_queries.json")


@pytest.fixture(scope="session")
def redteam() -> Dict[str, Any]:
    return _load_json("acl_redteam_cases.json")


@pytest.fixture(scope="session")
def facet_truth() -> Dict[str, Any]:
    return _load_json("facet_ground_truth.json")


@pytest.fixture(scope="session")
def backend() -> str:
    return os.environ.get("SEARCH_BACKEND", "mock").lower()


@pytest_asyncio.fixture
async def loaded_store(corpus, backend):
    """Fresh store pre-loaded with the 60-doc corpus (both tenants)."""
    from app.services.factory import get_lexical_store, reset_mock_store

    if backend in ("opensearch", "elasticsearch", "es", "os"):
        from app.services.opensearch_store import OpenSearchLexicalStore

        store = OpenSearchLexicalStore()
    else:
        store = reset_mock_store()

    tenants = {d["tenant_id"] for d in corpus["documents"]}
    for tid in tenants:
        await store.clear_tenant(tid)
        await store.ensure_tenant(tid)

    for doc in corpus["documents"]:
        fields = {
            k: doc[k]
            for k in (
                "title",
                "body_text",
                "comments_text",
                "file_path",
                "repository",
                "object_type",
                "source",
                "owner",
                "updated_at",
                "container_path",
                "language",
                "tags",
                "acl_filter_terms",
                "hidden_fields",
            )
            if k in doc
        }
        await store.index_document(
            tenant_id=doc["tenant_id"],
            document_id=doc["document_id"],
            fields=fields,
            deleted=bool(doc.get("deleted")),
        )
    return store
