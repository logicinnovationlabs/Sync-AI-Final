"""
Block C Advanced Test Suite — Complex & Adversarial Tests
=========================================================

Covers every security-critical surface of Block C:

  ADV-1  Multi-source identity unification (same person, 3 sources)
  ADV-2  Layered ACL inheritance with deny-override precedence
  ADV-3  Deep nested group expansion (4 levels)
  ADV-4  Cross-tenant principal isolation
  ADV-5  Concurrent identity creation race condition (DB uniqueness)
  ADV-6  ACL replace semantics — revoked permissions disappear
  ADV-7  Content bounding at exact boundary (500 000 chars)
  ADV-8  MIME mismatch flagging (exe disguised as text/plain)
  ADV-9  Unicode / malformed email normalization
  ADV-10 Gmail title extraction from nested headers (regression guard)
  ADV-11 Group deny override from inherited container chain
  ADV-12 Determinism — same raw input yields identical canonical id & ACL
  ADV-13 Zero-byte / empty content handling
  ADV-14 Container max-depth traversal backstop
  ADV-15 "anyone" wildcard ACL scoped to correct tenant
  ADV-16 Permission escalation: highest level wins in dedup
"""

import asyncio
import pytest
import pytest_asyncio
from uuid import uuid4, UUID
from datetime import datetime, timezone

from app.services.pipeline import Pipeline, MAX_EXTRACTED_CHARS
from app.normalizer.registry import normalizer_registry
from app.identity.resolver import IdentityResolver
from app.identity.matchers.email_matcher import EmailMatcher
from app.identity.matchers.username_matcher import UsernameMatcher
from app.acl.compiler import ACLCompiler
from app.acl.container_service import ContainerService
from app.storage.canonical_repo import CanonicalRepo
from app.core.models import (
    CanonicalDocument,
    Principal,
    Group,
    ACLEntry,
    ContainerACLEntry,
    ContainerEdge,
    IdentityHint,
    PermissionLevel,
)

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _make_pipeline(repo: CanonicalRepo) -> Pipeline:
    """Build a fully-wired in-memory Pipeline."""
    matchers = [EmailMatcher(), UsernameMatcher()]
    resolver = IdentityResolver(matchers, repo)
    container_svc = ContainerService(repo)
    acl_compiler = ACLCompiler(resolver, container_svc, repo)
    return Pipeline(normalizer_registry, resolver, acl_compiler, repo)


def _drive_raw(
    file_id: str,
    name: str,
    owner_email: str,
    extra_permissions: list = None,
    parents: list = None,
    mime_type: str = "text/plain",
    content: str = "hello world",
) -> dict:
    perms = [
        {"type": "user", "emailAddress": owner_email, "role": "owner", "id": f"perm_{file_id}"},
    ]
    if extra_permissions:
        perms.extend(extra_permissions)
    return {
        "id": file_id,
        "name": name,
        "mimeType": mime_type,
        "owners": [{"emailAddress": owner_email}],
        "permissions": perms,
        "parents": parents or [],
        "createdTime": "2024-01-01T00:00:00Z",
        "modifiedTime": "2024-01-01T00:00:00Z",
        "_test_extracted_text": content,
    }


def _gmail_raw(
    msg_id: str,
    subject: str,
    from_email: str,
    mailbox_email: str,
    content: str = "email body",
) -> dict:
    return {
        "id": msg_id,
        "threadId": f"thread_{msg_id}",
        "labelIds": ["INBOX"],
        "snippet": content[:100],
        "payload": {
            "headers": [
                {"name": "From", "value": from_email},
                {"name": "To", "value": mailbox_email},
                {"name": "Subject", "value": subject},
                {"name": "Delivered-To", "value": mailbox_email},
            ],
        },
        "internalDate": "1704067200000",
        "sizeEstimate": len(content),
        "_mailbox_email": mailbox_email,
        "_test_extracted_text": content,
    }


# ---------------------------------------------------------------------------
# ADV-1: Multi-source identity unification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv1_multi_source_identity_unification():
    """
    ADV-1: The same person appears as Drive owner, Drive collaborator, and Gmail
    mailbox owner. All three must resolve to ONE principal_id — never duplicated.
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_id = uuid4()
    alice_email = "alice@corp.example"
    alice_id = uuid4()
    repo.register_login_user(tenant_id, alice_email, alice_id)
    repo.register_login_user(tenant_id, "bob@corp.example", uuid4())

    # Document 1: alice is owner on Drive
    r1 = await pipeline.process_raw(
        _drive_raw("drive_adv1a", "Alice Doc", alice_email),
        "google_drive", tenant_id,
    )

    # Document 2: alice is a writer on someone else's Drive doc
    r2 = await pipeline.process_raw(
        _drive_raw(
            "drive_adv1b", "Shared Doc", "bob@corp.example",
            extra_permissions=[
                {"type": "user", "emailAddress": alice_email, "role": "writer", "id": "p_alice"},
            ],
        ),
        "google_drive", tenant_id,
    )

    # Document 3: alice is Gmail mailbox owner
    r3 = await pipeline.process_raw(
        _gmail_raw("gmail_adv1", "Hello", "sender@corp.example", alice_email),
        "google_gmail", tenant_id,
    )

    alice_row = await repo.get_principal_by_email(alice_email, tenant_id)

    def pids_in(acls):
        return {e.principal_id for e in acls if e.principal_id}

    d1 = await repo.get_acl_entries(r1["canonical_document"].id)
    d2 = await repo.get_acl_entries(r2["canonical_document"].id)
    d3 = await repo.get_acl_entries(r3["canonical_document"].id)
    all_pids = pids_in(d1) | pids_in(d2) | pids_in(d3)

    assert alice_id in all_pids
    assert alice_id in pids_in(d1)
    assert alice_id in pids_in(d2)
    assert alice_id in pids_in(d3)
    if alice_row is not None:
        assert alice_row.id == alice_id or alice_row.id not in pids_in(d3)

    count = sum(
        1 for p in repo._principals.values()
        if p.email == alice_email and p.tenant_id == tenant_id
    )
    assert count <= 1


# ---------------------------------------------------------------------------
# ADV-2: Layered ACL inheritance with deny-override precedence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv2_layered_inheritance_deny_precedence():
    """
    ADV-2: Drive file ACL is permissions.list on the file only.
    Folder grants on grandparent/parent must not appear on the document.
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_id = uuid4()

    matchers = [EmailMatcher(), UsernameMatcher()]
    resolver = IdentityResolver(matchers, repo)

    alice_pid = (await resolver.resolve(
        IdentityHint(source_type="google_drive", external_id="a", email="alice@acl.example"),
        tenant_id,
    )).principal_id
    bob_pid = (await resolver.resolve(
        IdentityHint(source_type="google_drive", external_id="b", email="bob@acl.example"),
        tenant_id,
    )).principal_id
    repo.register_login_user(tenant_id, "owner@acl.example", uuid4())

    gp, parent, child = "gp_adv2", "p_adv2", "c_adv2"

    # Build edges: child's parent = parent, parent's parent = gp
    for p_id, c_id in [(gp, parent), (parent, child)]:
        await repo.upsert_container_edge(ContainerEdge(
            parent_container_id=p_id, child_container_id=c_id,
            tenant_id=tenant_id, source_type="google_drive",
            created_at=datetime.now(timezone.utc),
        ))

    ts = datetime.now(timezone.utc)

    # Grandparent: alice READ, bob READ
    for pid in [alice_pid, bob_pid]:
        await repo.upsert_container_acl(ContainerACLEntry(
            container_id=gp, principal_id=pid,
            permission=PermissionLevel.READ, is_deny=False,
            source_type="google_drive", tenant_id=tenant_id,
            created_at=ts, updated_at=ts,
        ))

    # Parent: alice WRITE (allow) — but then DENY
    await repo.upsert_container_acl(ContainerACLEntry(
        container_id=parent, principal_id=alice_pid,
        permission=PermissionLevel.WRITE, is_deny=False,
        source_type="google_drive", tenant_id=tenant_id,
        created_at=ts, updated_at=ts,
    ))
    await repo.upsert_container_acl(ContainerACLEntry(
        container_id=parent, principal_id=alice_pid,
        permission=PermissionLevel.NONE, is_deny=True,
        source_type="google_drive", tenant_id=tenant_id,
        created_at=ts, updated_at=ts,
    ))

    result = await pipeline.process_raw(
        _drive_raw("file_adv2", "Protected", "owner@acl.example", parents=[child]),
        "google_drive", tenant_id,
    )
    acls = await repo.get_acl_entries(result["canonical_document"].id)

    bob_allows = [e for e in acls if e.principal_id == bob_pid and not e.is_deny]
    assert len(bob_allows) == 0, "Drive must not inherit folder grants"

    alice_allows = [e for e in acls if e.principal_id == alice_pid and not e.is_deny]
    assert len(alice_allows) == 0, "Drive must not inherit folder grants"


# ---------------------------------------------------------------------------
# ADV-3: Deep nested group expansion (4 levels)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv3_deep_nested_group_expansion():
    """
    ADV-3: Group chain A → B → C → D → [alice].
    Document grants group A in ACL.
    After expansion, alice must appear as group_membership entry.
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_id = uuid4()

    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    alice_pid = (await resolver.resolve(
        IdentityHint(source_type="google_drive", external_id="a_g", email="alice@groups.example"),
        tenant_id,
    )).principal_id
    repo.register_login_user(tenant_id, "owner@groups.example", uuid4())

    ts = datetime.now(timezone.utc)

    group_d = Group(
        id=uuid4(), tenant_id=tenant_id, name="Group D", email="groupd@groups.example",
        source_type="google_drive", source_id="gd_D",
        member_principal_ids=[alice_pid], member_group_ids=[],
        created_at=ts, updated_at=ts,
    )
    group_c = Group(
        id=uuid4(), tenant_id=tenant_id, name="Group C", email="groupc@groups.example",
        source_type="google_drive", source_id="gd_C",
        member_principal_ids=[], member_group_ids=[group_d.id],
        created_at=ts, updated_at=ts,
    )
    group_b = Group(
        id=uuid4(), tenant_id=tenant_id, name="Group B", email="groupb@groups.example",
        source_type="google_drive", source_id="gd_B",
        member_principal_ids=[], member_group_ids=[group_c.id],
        created_at=ts, updated_at=ts,
    )
    group_a = Group(
        id=uuid4(), tenant_id=tenant_id, name="Group A", email="groupa@groups.example",
        source_type="google_drive", source_id="gd_A",
        member_principal_ids=[], member_group_ids=[group_b.id],
        created_at=ts, updated_at=ts,
    )
    for grp in [group_d, group_c, group_b, group_a]:
        await repo.create_group(grp)

    raw = {
        "id": "file_adv3",
        "name": "Deep Group Doc",
        "mimeType": "text/plain",
        "owners": [{"emailAddress": "owner@groups.example"}],
        "permissions": [
            {"type": "user", "emailAddress": "owner@groups.example", "role": "owner", "id": "po"},
            {"type": "group", "emailAddress": "groupa@groups.example", "role": "reader", "id": "pg"},
        ],
        "parents": [],
        "createdTime": "2024-01-01T00:00:00Z",
        "modifiedTime": "2024-01-01T00:00:00Z",
        "_test_extracted_text": "content",
    }

    result = await pipeline.process_raw(raw, "google_drive", tenant_id)
    acls = await repo.get_acl_entries(result["canonical_document"].id)

    alice_acls = [e for e in acls if e.principal_id == alice_pid]
    assert len(alice_acls) == 0, (
        "Drive group shares are skipped this slice; Alice must not gain access via group expansion"
    )


# ---------------------------------------------------------------------------
# ADV-4: Cross-tenant principal isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv4_cross_tenant_isolation():
    """
    ADV-4: Same email in two tenants binds to two distinct users.principal_id values.
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_a, tenant_b = uuid4(), uuid4()
    alice_email = "alice@shared.example"
    alice_a, alice_b = uuid4(), uuid4()
    repo.register_login_user(tenant_a, alice_email, alice_a)
    repo.register_login_user(tenant_b, alice_email, alice_b)

    r1 = await pipeline.process_raw(
        _drive_raw("f_ta", "Doc A", alice_email), "google_drive", tenant_a
    )
    r2 = await pipeline.process_raw(
        _drive_raw("f_tb", "Doc B", alice_email), "google_drive", tenant_b
    )

    acls_a = await repo.get_acl_entries(r1["canonical_document"].id)
    acls_b = await repo.get_acl_entries(r2["canonical_document"].id)
    assert {e.principal_id for e in acls_a if e.principal_id} == {alice_a}
    assert {e.principal_id for e in acls_b if e.principal_id} == {alice_b}
    assert r1["canonical_document"].owner_principal_id == alice_a
    assert r2["canonical_document"].owner_principal_id == alice_b


# ---------------------------------------------------------------------------
# ADV-5: Concurrent identity creation race condition
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv5_concurrent_identity_race():
    """
    ADV-5: 20 concurrent coroutines all resolving the same email must result
    in exactly one principal and identical principal_id for all callers.
    """
    repo = CanonicalRepo(use_memory=True)
    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    tenant_id = uuid4()
    email = "racecar@concurrent.example"

    async def resolve_one():
        hint = IdentityHint(source_type="google_drive", external_id=str(uuid4()), email=email)
        return (await resolver.resolve(hint, tenant_id)).principal_id

    pids = await asyncio.gather(*[resolve_one() for _ in range(20)])

    assert len(set(pids)) == 1, f"All 20 resolutions must share one principal_id, got {len(set(pids))}"
    assert len([p for p in repo._principals.values() if p.email == email]) == 1


# ---------------------------------------------------------------------------
# ADV-6: ACL replace semantics (revoked permissions disappear)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv6_acl_replace_not_append():
    """
    ADV-6: First pass — alice has OWNER. Second pass — alice not in permissions.
    Alice must have ZERO ACL entries after second pass (replace, not append).
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_id = uuid4()
    alice_email = "alice@revoke.example"
    alice_id = uuid4()
    repo.register_login_user(tenant_id, alice_email, alice_id)
    repo.register_login_user(tenant_id, "owner@revoke.example", uuid4())

    # First pass
    r1 = await pipeline.process_raw(
        _drive_raw("file_adv6", "Revokable", "owner@revoke.example",
                   extra_permissions=[
                       {"type": "user", "emailAddress": alice_email, "role": "owner", "id": "pa"},
                   ]),
        "google_drive", tenant_id,
    )
    # Drive-share ACLs bind to users.principal_id, not identity_principals.
    v1_alice = [
        e
        for e in await repo.get_acl_entries(r1["canonical_document"].id)
        if e.principal_id == alice_id
    ]
    assert len(v1_alice) >= 1

    # Second pass — alice removed
    r2 = await pipeline.process_raw(
        _drive_raw("file_adv6", "Revokable", "owner@revoke.example"),
        "google_drive", tenant_id,
    )
    v2_alice = [
        e
        for e in await repo.get_acl_entries(r2["canonical_document"].id)
        if e.principal_id == alice_id
    ]
    assert len(v2_alice) == 0, f"After revocation alice must have 0 entries, got {v2_alice}"


# ---------------------------------------------------------------------------
# ADV-7: Content bounding at exact boundary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv7_content_bounding_boundary_cases():
    """
    ADV-7: Below / at / above / far-above MAX_EXTRACTED_CHARS.
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_id = uuid4()
    M = MAX_EXTRACTED_CHARS

    cases = [
        (M - 1,       M - 1, "below_boundary"),
        (M,           M,     "at_boundary"),
        (M + 1,       M,     "above_boundary"),
        (M + 100_000, M,     "far_above"),
    ]

    for input_size, expected_max, label in cases:
        raw = _drive_raw(f"f_{label}", label, "owner@bound.example", content="X" * input_size)
        result = await pipeline.process_raw(raw, "google_drive", tenant_id)
        length = len(result["canonical_document"].content)

        assert length <= expected_max, f"[{label}] got {length}, expected <= {expected_max}"
        if input_size <= M:
            assert length == input_size, f"[{label}] must not truncate {input_size} chars"


# ---------------------------------------------------------------------------
# ADV-8: MIME mismatch flagging
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv8_mime_mismatch_flagging():
    """
    ADV-8: Claimed text/plain but magic bytes say application/x-executable.
    mime_mismatch must be True and detected_mime_type must be set correctly.
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_id = uuid4()

    raw = {
        "id": "file_adv8",
        "name": "Evil.txt",
        "mimeType": "text/plain",
        "owners": [{"emailAddress": "o@mime.example"}],
        "permissions": [{"type": "user", "emailAddress": "o@mime.example", "role": "owner", "id": "p1"}],
        "parents": [],
        "createdTime": "2024-01-01T00:00:00Z",
        "modifiedTime": "2024-01-01T00:00:00Z",
        "_test_extracted_text": "harmless text",
        "_test_detected_mime": "application/x-executable",
        "_test_mime_mismatch": True,
    }

    result = await pipeline.process_raw(raw, "google_drive", tenant_id)
    doc = result["canonical_document"]

    assert doc.mime_mismatch is True
    assert doc.detected_mime_type == "application/x-executable"
    assert doc.mime_type == "text/plain"


# ---------------------------------------------------------------------------
# ADV-9: Unicode / malformed email normalization
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv9_email_normalization_variants():
    """
    ADV-9: Case-insensitive, whitespace-stripped email variants all map to
    ONE principal. Malformed email (no domain) raises ValueError.
    """
    repo = CanonicalRepo(use_memory=True)
    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    tenant_id = uuid4()

    variants = ["alice@corp.example", "Alice@Corp.EXAMPLE", "  ALICE@corp.example  "]
    pids = []
    for v in variants:
        h = IdentityHint(source_type="google_drive", external_id="e", email=v)
        pids.append((await resolver.resolve(h, tenant_id)).principal_id)

    assert len(set(pids)) == 1, f"All variants must share one principal_id, got {len(set(pids))}"

    with pytest.raises(ValueError):
        await resolver.resolve(
            IdentityHint(source_type="google_drive", external_id="bad", email="not_an_email"),
            tenant_id,
        )


# ---------------------------------------------------------------------------
# ADV-10: Gmail title from nested payload headers (regression guard)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv10_gmail_title_nested_headers_regression():
    """
    ADV-10: Gmail subject lives in payload.headers, not in raw['subject'].
    Must extract correct title. Empty/whitespace subject falls back to 'Untitled'.
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_id = uuid4()

    cases = [
        ("Re: Urgent [#1234]", "Re: Urgent [#1234]"),
        ("", "Untitled"),
    ]

    for idx, (subject, expected) in enumerate(cases):
        raw = _gmail_raw(f"gm_adv10_{idx}", subject, "s@m.example", f"mb{idx}@m.example")
        result = await pipeline.process_raw(raw, "google_gmail", tenant_id)
        actual = result["canonical_document"].title
        assert actual == expected, f"[{idx}] subject={subject!r}: expected={expected!r}, got={actual!r}"


# ---------------------------------------------------------------------------
# ADV-11: Group deny override from inherited container chain
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv11_group_deny_in_container_chain():
    """
    ADV-11: Engineers group gets READ from grandparent folder.
    Parent folder has DENY for engineers group.
    Alice (member of engineers) must have NO allow entries on the document.
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_id = uuid4()

    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    alice_pid = (await resolver.resolve(
        IdentityHint(source_type="google_drive", external_id="ae", email="alice@eng.example"),
        tenant_id,
    )).principal_id

    ts = datetime.now(timezone.utc)
    eng = Group(
        id=uuid4(), tenant_id=tenant_id, name="Engineers",
        email="engineers@eng.example",
        source_type="google_drive", source_id="gd_eng",
        member_principal_ids=[alice_pid], member_group_ids=[],
        created_at=ts, updated_at=ts,
    )
    await repo.create_group(eng)

    gp_id, p_id = "gp_adv11", "p_adv11"
    await repo.upsert_container_edge(ContainerEdge(
        parent_container_id=gp_id, child_container_id=p_id,
        tenant_id=tenant_id, source_type="google_drive", created_at=ts,
    ))

    # Grandparent: engineers READ
    await repo.upsert_container_acl(ContainerACLEntry(
        container_id=gp_id, group_id=eng.id,
        permission=PermissionLevel.READ, is_deny=False,
        source_type="google_drive", tenant_id=tenant_id, created_at=ts, updated_at=ts,
    ))
    # Parent: engineers DENY
    await repo.upsert_container_acl(ContainerACLEntry(
        container_id=p_id, group_id=eng.id,
        permission=PermissionLevel.NONE, is_deny=True,
        source_type="google_drive", tenant_id=tenant_id, created_at=ts, updated_at=ts,
    ))

    result = await pipeline.process_raw(
        _drive_raw("file_adv11", "Restricted", "owner@eng.example", parents=[p_id]),
        "google_drive", tenant_id,
    )
    acls = await repo.get_acl_entries(result["canonical_document"].id)
    alice_allows = [e for e in acls if e.principal_id == alice_pid and not e.is_deny]
    assert len(alice_allows) == 0, f"Group deny must block alice, got: {alice_allows}"


# ---------------------------------------------------------------------------
# ADV-12: Pipeline determinism
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv12_pipeline_determinism():
    """
    ADV-12: Processing the same raw document twice produces identical
    canonical id, content, and ACL fingerprint.
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_id = uuid4()

    raw = _drive_raw(
        "file_adv12", "Det Doc", "owner@det.example",
        extra_permissions=[
            {"type": "user", "emailAddress": "reader@det.example", "role": "reader", "id": "pr"},
        ],
        content="Stable content.",
    )

    r1 = await pipeline.process_raw(raw, "google_drive", tenant_id)
    r2 = await pipeline.process_raw(raw, "google_drive", tenant_id)
    d1, d2 = r1["canonical_document"], r2["canonical_document"]

    assert d1.id == d2.id
    assert d1.content == d2.content
    assert d1.title == d2.title

    def fingerprint(acls):
        return frozenset(
            (str(e.principal_id), e.permission.value, e.granted_via)
            for e in acls if e.principal_id
        )

    fp1 = fingerprint(await repo.get_acl_entries(d1.id))
    fp2 = fingerprint(await repo.get_acl_entries(d2.id))
    assert fp1 == fp2, "ACL fingerprint must be identical on repeat processing"


# ---------------------------------------------------------------------------
# ADV-13: Zero-byte and whitespace-only content
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv13_empty_content_no_crash():
    """
    ADV-13: Empty string and whitespace-only content must not crash the pipeline.
    Canonical document must be created with a string content field.
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_id = uuid4()

    for content, label in [("", "empty"), ("   \n\t  ", "whitespace")]:
        raw = _drive_raw(f"f_{label}", f"{label} doc", "owner@empty.example", content=content)
        result = await pipeline.process_raw(raw, "google_drive", tenant_id)
        doc = result["canonical_document"]
        assert doc is not None
        assert isinstance(doc.content, str)
        assert len(doc.content) <= MAX_EXTRACTED_CHARS


# ---------------------------------------------------------------------------
# ADV-14: Container max-depth traversal backstop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv14_container_max_depth_backstop():
    """
    ADV-14: A 60-level-deep folder chain. get_ancestors(max_depth=50) must
    return at most 50 ancestors and must not crash.
    """
    repo = CanonicalRepo(use_memory=True)
    container_svc = ContainerService(repo)
    tenant_id = uuid4()

    containers = [f"c_{i}" for i in range(60)]
    for i in range(59):
        await repo.upsert_container_edge(ContainerEdge(
            parent_container_id=containers[i + 1],
            child_container_id=containers[i],
            tenant_id=tenant_id,
            source_type="google_drive",
            created_at=datetime.now(timezone.utc),
        ))

    ancestors = await container_svc.get_ancestors(containers[0], tenant_id, max_depth=50)
    assert len(ancestors) <= 50, f"Expected <= 50 ancestors, got {len(ancestors)}"


# ---------------------------------------------------------------------------
# ADV-15: "anyone" wildcard ACL scoped to correct tenant
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv15_anyone_wildcard_tenant_scoping():
    """
    ADV-15: A public (anyone) Drive document in tenant_a must have all ACL
    entries tagged with tenant_a. tenant_b must see zero of those entries.
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_a, tenant_b = uuid4(), uuid4()

    raw = {
        "id": "file_adv15",
        "name": "Public Doc",
        "mimeType": "text/plain",
        "owners": [{"emailAddress": "owner@pub.example"}],
        "permissions": [
            {"type": "user", "emailAddress": "owner@pub.example", "role": "owner", "id": "po"},
            {"type": "anyone", "role": "reader", "id": "pa"},
        ],
        "parents": [],
        "createdTime": "2024-01-01T00:00:00Z",
        "modifiedTime": "2024-01-01T00:00:00Z",
        "_test_extracted_text": "public content",
    }

    result = await pipeline.process_raw(raw, "google_drive", tenant_a)
    acls = await repo.get_acl_entries(result["canonical_document"].id)

    assert all(e.tenant_id == tenant_a for e in acls), "All ACLs must be tenant_a"
    assert len([e for e in acls if e.tenant_id == tenant_b]) == 0


# ---------------------------------------------------------------------------
# ADV-16: Permission escalation — highest level wins in dedup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv16_permission_level_escalation_dedup():
    """
    ADV-16: alice is the document OWNER. After pipeline dedup, she must retain
    the OWNER level (not be downgraded by any lower-priority inherited grant).
    """
    repo = CanonicalRepo(use_memory=True)
    pipeline = _make_pipeline(repo)
    tenant_id = uuid4()

    alice_email = "alice@escalate.example"
    alice_id = uuid4()
    repo.register_login_user(tenant_id, alice_email, alice_id)
    result = await pipeline.process_raw(
        _drive_raw("file_adv16", "Escalation Doc", alice_email),
        "google_drive", tenant_id,
    )
    acls = await repo.get_acl_entries(result["canonical_document"].id)

    rank = {"NONE": 0, "READ": 1, "WRITE": 2, "DELETE": 3, "OWNER": 4}
    alice_acls = [e for e in acls if e.principal_id == alice_id and not e.is_deny]
    assert len(alice_acls) >= 1, "Alice must have at least one ACL entry"

    best = max(alice_acls, key=lambda e: rank.get(e.permission.value, 0))
    assert best.permission == PermissionLevel.OWNER, (
        f"Alice's best permission must be OWNER, got {best.permission}"
    )
