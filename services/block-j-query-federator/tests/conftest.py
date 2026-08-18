"""Shared pytest fixtures for Block J signoff tests."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

# Ensure test defaults before app imports
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ACL_BACKEND", "memory")
os.environ.setdefault("RERANKER_BACKEND", "mock")
os.environ.setdefault("EMBEDDING_BACKEND", "mock")
os.environ.setdefault("ENFORCE_TENANT_ISOLATION", "true")
os.environ.setdefault("BACKEND_TIMEOUT_SECONDS", "2.0")
os.environ.setdefault("BACKEND_CONNECT_TIMEOUT_SECONDS", "1.0")
os.environ.setdefault("LEXICAL_SEARCH_URL", "http://127.0.0.1:8086")
os.environ.setdefault("VECTOR_SEARCH_URL", "http://127.0.0.1:8087")
os.environ.setdefault("GRAPH_SERVICE_URL", "http://127.0.0.1:8088")
os.environ.setdefault("EMBEDDING_MODEL_VERSION", "text-embedding-3-large")
os.environ.setdefault("EMBEDDING_DIMENSIONS", "64")

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(os.environ.get("FIXTURES_PATH") or (ROOT / "fixtures"))


def _use_real_services() -> bool:
    return os.environ.get("USE_REAL_SERVICES", "").lower() in ("1", "true", "yes")


def _load_json(name: str) -> Dict[str, Any]:
    path = FIXTURES / name
    if not path.exists():
        # Auto-generate if missing
        from fixtures.generate_fixtures import OUT  # noqa: F401

        gen = ROOT / "fixtures" / "generate_fixtures.py"
        import runpy

        runpy.run_path(str(gen))
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_bearer(
    tenant_id: str,
    principal_id: str = "user:alice",
    groups: list | None = None,
    scopes: list | None = None,
) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "principal_id": principal_id,
                "groups": groups or ["group:eng"],
                "scopes": scopes or ["search.read"],
            }
        ).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.testsig"


class _KillAwareLexical:
    """Lexical client that honors mock kill flags and always sends a tenant JWT."""

    def __init__(self, inner) -> None:
        self._inner = inner

    async def search(self, **kwargs):
        from mocks.backend_server import corpus as mock_corpus

        if mock_corpus.kill_lexical:
            raise httpx.ConnectError("lexical killed")
        if not kwargs.get("authorization"):
            kwargs["authorization"] = f"Bearer {make_bearer(kwargs['tenant_id'])}"
        return await self._inner.search(**kwargs)


class _KillAwareVector:
    def __init__(self, inner) -> None:
        self._inner = inner

    async def search(self, **kwargs):
        from mocks.backend_server import corpus as mock_corpus

        if mock_corpus.kill_vector:
            raise httpx.ConnectError("vector killed")
        if not kwargs.get("authorization"):
            kwargs["authorization"] = f"Bearer {make_bearer(kwargs['tenant_id'])}"
        return await self._inner.search(**kwargs)


class _KillAwareGraph:
    def __init__(self, inner) -> None:
        self._inner = inner

    async def fetch_signals(self, **kwargs):
        from mocks.backend_server import corpus as mock_corpus

        if mock_corpus.kill_graph:
            raise httpx.ConnectError("graph killed")
        if not kwargs.get("authorization"):
            kwargs["authorization"] = f"Bearer {make_bearer(kwargs['tenant_id'])}"
        return await self._inner.fetch_signals(**kwargs)


@pytest.fixture(scope="session")
def seeded_real_backends(corpus) -> bool:
    """Index J corpus into live F (OpenSearch) and G (Qdrant) when Phase 2."""
    if not _use_real_services():
        return False

    from app.clients.embedding import EmbeddingClient

    lexical_url = os.environ["LEXICAL_SEARCH_URL"].rstrip("/")
    vector_url = os.environ["VECTOR_SEARCH_URL"].rstrip("/")
    graph_url = os.environ["GRAPH_SERVICE_URL"].rstrip("/")
    model_version = os.environ.get("EMBEDDING_MODEL_VERSION", "text-embedding-3-large")
    embedder = EmbeddingClient()

    with httpx.Client(timeout=30.0) as client:
        for url, name in (
            (lexical_url, "F"),
            (vector_url, "G"),
            (graph_url, "H"),
        ):
            try:
                health = client.get(f"{url}/health")
            except httpx.HTTPError as exc:
                pytest.fail(f"Phase 2 {name} not reachable at {url}/health: {exc}")
            if health.status_code >= 500:
                pytest.fail(f"Phase 2 {name} health {health.status_code}: {health.text}")

        for doc in corpus["documents"]:
            tid = doc["tenant_id"]
            headers = {"Authorization": f"Bearer {make_bearer(tid)}"}
            fields = {
                "title": doc.get("title") or "",
                "body_text": doc.get("body_text") or "",
                "acl_filter_terms": doc.get("acl_filter_terms") or [],
                "object_type": doc.get("object_type") or "",
                "source": doc.get("source") or "",
                "owner": doc.get("owner") or "",
                "tags": list(doc.get("tags") or []),
            }
            idx = client.post(
                f"{lexical_url}/_internal/index",
                headers=headers,
                json={
                    "document_id": doc["document_id"],
                    "tenant_id": tid,
                    "fields": fields,
                    "deleted": bool(doc.get("deleted")),
                },
            )
            idx.raise_for_status()
            text = f"{doc.get('title', '')} {doc.get('body_text', '')}"
            ingest = client.post(
                f"{vector_url}/api/v1/ingest",
                headers=headers,
                json={
                    "tenant_id": tid,
                    "chunk_id": doc["document_id"],
                    "document_id": doc["document_id"],
                    "embedding": embedder._embed_mock(text),
                    "model_version": model_version,
                    "chunk_text": (doc.get("body_text") or "")[:2000],
                    "acl_filter_terms": doc.get("acl_filter_terms") or [],
                },
            )
            ingest.raise_for_status()
    return True


@pytest.fixture(scope="session")
def corpus() -> Dict[str, Any]:
    return _load_json("corpus.json")


@pytest.fixture(scope="session")
def redteam() -> Dict[str, Any]:
    return _load_json("acl_redteam_cases.json")


@pytest.fixture(scope="session")
def relevance() -> Dict[str, Any]:
    return _load_json("relevance_labels.json")


@pytest.fixture(scope="session")
def representative_queries() -> Dict[str, Any]:
    return _load_json("representative_queries.json")


@pytest.fixture(scope="session")
def acl_entries() -> Dict[str, Any]:
    return _load_json("acl_entries.json")


@pytest_asyncio.fixture
async def mock_backends(corpus):
    """ASGI mock F/G/H sharing one corpus; returns (app, base_url via ASGI)."""
    from mocks.backend_server import create_mock_app, load_documents

    load_documents(corpus["documents"])
    app = create_mock_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://mock") as client:
        yield client, app


@pytest_asyncio.fixture
async def federator_stack(corpus, acl_entries, mock_backends, seeded_real_backends):
    """Federator wired to mock backends, or real F/G/H when USE_REAL_SERVICES=1."""
    from app.clients.embedding import EmbeddingClient
    from app.clients.graph import GraphClient
    from app.clients.lexical import LexicalClient
    from app.clients.vector import VectorClient
    from app.services.permission import ACLEntryRecord, ACLStore, InMemoryACLStore
    from app.services.ranker import Ranker
    from app.services.federator import Federator

    store = InMemoryACLStore()
    store.replace_all(
        [
            ACLEntryRecord(
                doc_id=e["doc_id"],
                principal_id=e.get("principal_id"),
                group_id=e.get("group_id"),
                permission_type=e.get("permission_type", "read"),
                is_deny=bool(e.get("is_deny")),
                tenant_id=e.get("tenant_id", ""),
            )
            for e in acl_entries["entries"]
        ]
    )

    ranker = Ranker(backend="mock", enabled=True)
    ranker.load()

    if _use_real_services():
        lexical_url = os.environ["LEXICAL_SEARCH_URL"].rstrip("/")
        vector_url = os.environ["VECTOR_SEARCH_URL"].rstrip("/")
        graph_url = os.environ["GRAPH_SERVICE_URL"].rstrip("/")
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            federator = Federator(
                http_client=http_client,
                ranker=ranker,
                embedding_client=EmbeddingClient(http_client),
                lexical=_KillAwareLexical(LexicalClient(http_client, base_url=lexical_url)),
                vector=_KillAwareVector(VectorClient(http_client, base_url=vector_url)),
                graph=_KillAwareGraph(GraphClient(http_client, base_url=graph_url)),
                acl_store=ACLStore(memory=store),
            )
            yield federator, store, http_client
        return

    http_client, _app = mock_backends
    base = "http://mock"
    federator = Federator(
        http_client=http_client,
        ranker=ranker,
        embedding_client=EmbeddingClient(http_client),
        lexical=LexicalClient(http_client, base_url=base),
        vector=VectorClient(http_client, base_url=base),
        graph=GraphClient(http_client, base_url=base),
        acl_store=ACLStore(memory=store),
    )
    yield federator, store, http_client


@pytest_asyncio.fixture
async def api_client(corpus, acl_entries):
    """Full FastAPI app client with federator pointed at ASGI mock backends."""
    from mocks.backend_server import create_mock_app, load_documents
    from app.services.permission import ACLEntryRecord, ACLStore, memory_acl_store

    load_documents(corpus["documents"])
    memory_acl_store.replace_all(
        [
            ACLEntryRecord(
                doc_id=e["doc_id"],
                principal_id=e.get("principal_id"),
                group_id=e.get("group_id"),
                permission_type=e.get("permission_type", "read"),
                is_deny=bool(e.get("is_deny")),
                tenant_id=e.get("tenant_id", ""),
            )
            for e in acl_entries["entries"]
        ]
    )

    mock_app = create_mock_app()
    mock_transport = ASGITransport(app=mock_app)

    from app.main import app, get_federator
    from app.clients.embedding import EmbeddingClient
    from app.clients.graph import GraphClient
    from app.clients.lexical import LexicalClient
    from app.clients.vector import VectorClient
    from app.services.federator import Federator
    from app.services.ranker import Ranker

    async with httpx.AsyncClient(
        transport=mock_transport, base_url="http://mock"
    ) as backend_client:
        ranker = Ranker(backend="mock", enabled=True)
        ranker.load()
        fed = Federator(
            http_client=backend_client,
            ranker=ranker,
            embedding_client=EmbeddingClient(backend_client),
            lexical=LexicalClient(backend_client, base_url="http://mock"),
            vector=VectorClient(backend_client, base_url="http://mock"),
            graph=GraphClient(backend_client, base_url="http://mock"),
            acl_store=ACLStore(memory=memory_acl_store),
        )
        app.dependency_overrides[get_federator] = lambda: fed
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            yield client, mock_app
        app.dependency_overrides.clear()
