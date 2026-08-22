"""Unit tests for the shared deny-override ACL filter (app.acl.filter)."""

import pytest

from app.acl.filter import acl_terms_from_jwt, document_is_visible, is_fail_closed
from app.services.vector.mock_store import MockVectorStore


def test_fail_closed_empty_acl():
    assert is_fail_closed([])
    assert not document_is_visible([], ["user:alice"])


def test_missing_acl_terms_are_deny():
    assert not document_is_visible(["user:alice"], [])
    assert not document_is_visible(["user:alice"], None)


def test_allow_match():
    assert document_is_visible(["user:alice", "group:eng"], ["group:eng"])


def test_explicit_deny_wins_over_group_allow():
    doc = ["group:eng", "deny:user:bob"]
    assert document_is_visible(["user:alice", "group:eng"], doc)
    assert not document_is_visible(["user:bob", "group:eng"], doc)


def test_bypass_star():
    assert document_is_visible(["*"], ["deny:user:bob", "group:eng"])


def test_acl_terms_from_jwt_ignores_star_and_uses_sub():
    terms = acl_terms_from_jwt(
        {
            "sub": "alice",
            "acl_terms": ["*", "user:eve"],
            "groups": ["eng"],
        }
    )
    assert "*" not in terms
    assert "alice" in terms
    assert "user:alice" in terms
    assert "user:eve" in terms
    assert "eng" in terms
    assert "group:eng" in terms


def test_acl_terms_from_jwt_empty_payload_is_fail_closed():
    assert is_fail_closed(acl_terms_from_jwt({}))


@pytest.mark.asyncio
async def test_vector_mock_does_not_leak_denied_chunk():
    store = MockVectorStore()
    tenant = "t-deny"
    embedding = [0.1, 0.2, 0.3]
    await store.upsert_chunk(
        tenant_id=tenant,
        chunk_id="open",
        document_id="d1",
        embedding=embedding,
        model_version="v1",
        acl_terms=["group:eng"],
        chunk_text="open to eng",
    )
    await store.upsert_chunk(
        tenant_id=tenant,
        chunk_id="denied-bob",
        document_id="d2",
        embedding=embedding,
        model_version="v1",
        acl_terms=["group:eng", "deny:user:bob"],
        chunk_text="secret except bob",
    )

    alice = await store.search(tenant, embedding, ["user:alice", "group:eng"], top_k=10)
    bob = await store.search(tenant, embedding, ["user:bob", "group:eng"], top_k=10)

    assert {r["chunk_id"] for r in alice} == {"open", "denied-bob"}
    assert {r["chunk_id"] for r in bob} == {"open"}
