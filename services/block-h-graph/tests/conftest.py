"""Shared pytest fixtures for Block H signoff tests."""

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
os.environ.setdefault("GRAPH_BACKEND", os.environ.get("GRAPH_BACKEND", "mock"))
os.environ.setdefault("ENFORCE_TENANT_ISOLATION", "true")

_FIXTURES_ENV = os.environ.get("FIXTURES_PATH")
FIXTURES = Path(_FIXTURES_ENV) if _FIXTURES_ENV else (ROOT / "fixtures")


def _load_json(name: str) -> Dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_bearer(
    tenant_id: str,
    principal_id: str = "user:alice",
    scopes=None,
) -> str:
    if scopes is None:
        scopes = ["graph.read", "people.read", "graph.admin"]
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "principal_id": principal_id,
                "scopes": scopes,
            }
        ).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.testsig"


@pytest.fixture(scope="session")
def graph_edges() -> Dict[str, Any]:
    return _load_json("graph_edges.json")


@pytest.fixture(scope="session")
def principals() -> Dict[str, Any]:
    return _load_json("principals.json")


@pytest.fixture(scope="session")
def documents() -> Dict[str, Any]:
    return _load_json("documents.json")


@pytest.fixture(scope="session")
def backend() -> str:
    return os.environ.get("GRAPH_BACKEND", "mock").lower()


async def _load_reference_graph(store, graph_edges, principals, documents):
    """Populate store from Block Z-shaped fixtures (direct import)."""
    tenant_id = graph_edges["tenant_id"]
    await store.clear_tenant(tenant_id)
    await store.ensure_tenant(tenant_id)

    for person in principals["people"]:
        props = {k: v for k, v in person.items() if k != "source_id"}
        await store.upsert_node(tenant_id, "Person", person["source_id"], props)

    for group in principals["groups"]:
        props = {k: v for k, v in group.items() if k != "source_id"}
        await store.upsert_node(tenant_id, "Group", group["source_id"], props)

    for doc in documents["documents"]:
        label = doc.get("label", "Document")
        await store.upsert_node(
            tenant_id,
            label,
            doc["source_id"],
            {"title": doc.get("title"), "owner": doc.get("owner")},
        )

    for edge in graph_edges["edges"]:
        await store.upsert_edge(
            tenant_id,
            edge["relationship_type"],
            edge["source_id"],
            edge["target_id"],
            edge.get("properties") or {},
        )
    return tenant_id


@pytest_asyncio.fixture
async def loaded_store(graph_edges, principals, documents, backend):
    from app.services.factory import get_graph_store, reset_mock_store

    if backend == "neo4j":
        store = get_graph_store("neo4j")
    else:
        store = reset_mock_store()

    tenant_id = await _load_reference_graph(store, graph_edges, principals, documents)
    store._test_tenant_id = tenant_id  # type: ignore[attr-defined]
    return store
