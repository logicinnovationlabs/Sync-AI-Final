"""Unit tests for ACL post-check."""

from __future__ import annotations

import pytest

from app.models import UserContext
from app.services.permission import (
    ACLEntryRecord,
    InMemoryACLStore,
    check_documents_access,
)


@pytest.mark.asyncio
async def test_allow_by_principal():
    store = InMemoryACLStore()
    store.add(
        ACLEntryRecord(
            doc_id="doc-1",
            principal_id="user:alice",
            permission_type="read",
            tenant_id="t1",
        )
    )
    user = UserContext(tenant_id="t1", principal_id="user:alice", groups=[])
    allowed = await check_documents_access(["doc-1", "doc-2"], user, store=store)
    assert allowed == {"doc-1"}


@pytest.mark.asyncio
async def test_allow_by_group():
    store = InMemoryACLStore()
    store.add(
        ACLEntryRecord(
            doc_id="doc-1",
            group_id="group:eng",
            permission_type="read",
            tenant_id="t1",
        )
    )
    user = UserContext(
        tenant_id="t1",
        principal_id="user:bob",
        groups=["group:eng"],
    )
    allowed = await check_documents_access(["doc-1"], user, store=store)
    assert allowed == {"doc-1"}


@pytest.mark.asyncio
async def test_deny_overrides_allow():
    store = InMemoryACLStore()
    store.add(
        ACLEntryRecord(
            doc_id="doc-1",
            group_id="group:eng",
            permission_type="read",
            tenant_id="t1",
        )
    )
    store.add(
        ACLEntryRecord(
            doc_id="doc-1",
            principal_id="user:bob",
            permission_type="read",
            is_deny=True,
            tenant_id="t1",
        )
    )
    user = UserContext(
        tenant_id="t1",
        principal_id="user:bob",
        groups=["group:eng"],
    )
    allowed = await check_documents_access(["doc-1"], user, store=store)
    assert allowed == set()


@pytest.mark.asyncio
async def test_fail_closed_without_rows():
    store = InMemoryACLStore()
    user = UserContext(tenant_id="t1", principal_id="user:alice", groups=["group:eng"])
    allowed = await check_documents_access(["doc-missing"], user, store=store)
    assert allowed == set()


@pytest.mark.asyncio
async def test_tenant_isolation_in_memory():
    store = InMemoryACLStore()
    store.add(
        ACLEntryRecord(
            doc_id="doc-1",
            principal_id="user:alice",
            permission_type="read",
            tenant_id="tenant-a",
        )
    )
    user = UserContext(tenant_id="tenant-b", principal_id="user:alice", groups=[])
    allowed = await check_documents_access(["doc-1"], user, store=store)
    assert allowed == set()
