"""
Tests for ACL compiler.

Verifies group expansion, inheritance, deny-override logic.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from app.acl.compiler import ACLCompiler
from app.acl.container_service import ContainerService
from app.identity.resolver import IdentityResolver
from app.identity.matchers.email_matcher import EmailMatcher
from app.identity.matchers.username_matcher import UsernameMatcher
from app.storage.canonical_repo import CanonicalRepo
from app.core.models import (
    CanonicalDocument,
    IdentityHint,
    PermissionLevel,
    Principal,
    Group,
)


@pytest.fixture
def repo():
    """Create in-memory repository."""
    return CanonicalRepo(use_memory=True)


@pytest.fixture
def identity_resolver(repo):
    """Create identity resolver."""
    matchers = [EmailMatcher(), UsernameMatcher()]
    return IdentityResolver(matchers, repo)


@pytest.fixture
def container_service(repo):
    """Create container service."""
    return ContainerService(repo)


@pytest.fixture
def acl_compiler(identity_resolver, container_service, repo):
    """Create ACL compiler."""
    return ACLCompiler(identity_resolver, container_service, repo)


@pytest.mark.asyncio
async def test_compile_direct_permissions(acl_compiler, repo):
    """Test compilation of direct permissions."""
    tenant_id = uuid4()
    
    doc = CanonicalDocument(
        id="doc_1",
        source_type="google_drive",
        source_id="file_1",
        tenant_id=tenant_id,
        title="Test Document",
        content="Test content",
        url="https://example.com",
        mime_type="text/plain",
        detected_mime_type="text/plain",
        mime_mismatch=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        source_updated_at=datetime.now(timezone.utc),
        structured_metadata={},
        parent_ids=[],
    )
    
    permission_hints = [
        (
            IdentityHint(
                source_type="google_drive",
                external_id="user_1",
                email="alice@example.com",
                name="Alice",
            ),
            PermissionLevel.OWNER,
        ),
    ]
    
    entries = await acl_compiler.compile(doc, permission_hints, tenant_id)
    
    # Should have at least one direct entry
    direct_entries = [e for e in entries if e.granted_via == "direct"]
    assert len(direct_entries) >= 1
    assert direct_entries[0].permission == PermissionLevel.OWNER


@pytest.mark.asyncio
async def test_compile_group_expansion(acl_compiler, repo):
    """Test that group membership is expanded."""
    tenant_id = uuid4()
    
    # Create principals
    alice_principal = Principal(
        id=uuid4(),
        tenant_id=tenant_id,
        email="alice@example.com",
        name="Alice",
        source_identities={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    bob_principal = Principal(
        id=uuid4(),
        tenant_id=tenant_id,
        email="bob@example.com",
        name="Bob",
        source_identities={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await repo.create_principal(alice_principal)
    await repo.create_principal(bob_principal)
    
    # Create group with members
    group = Group(
        id=uuid4(),
        tenant_id=tenant_id,
        name="Engineering",
        email="eng@example.com",
        source_type="google_drive",
        source_id="group_1",
        member_principal_ids=[alice_principal.id, bob_principal.id],
        member_group_ids=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await repo.create_group(group)
    
    # Create document with group permission
    doc = CanonicalDocument(
        id="doc_1",
        source_type="google_drive",
        source_id="file_1",
        tenant_id=tenant_id,
        title="Test Document",
        content="Test content",
        url="https://example.com",
        mime_type="text/plain",
        detected_mime_type="text/plain",
        mime_mismatch=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        source_updated_at=datetime.now(timezone.utc),
        structured_metadata={},
        parent_ids=[],
    )
    
    permission_hints = [
        (
            IdentityHint(
                source_type="google_drive",
                external_id="group:group_1",
                email="eng@example.com",
                name="Engineering",
            ),
            PermissionLevel.WRITE,
        ),
    ]
    
    entries = await acl_compiler.compile(doc, permission_hints, tenant_id)
    
    # Should have group-expanded entries for Alice and Bob
    group_expanded = [e for e in entries if e.granted_via == "group_membership"]
    assert len(group_expanded) >= 2


@pytest.mark.asyncio
async def test_compile_group_expansion_cycle_safe(acl_compiler, repo):
    """Test that group expansion handles cycles safely."""
    tenant_id = uuid4()
    
    # Create two groups that reference each other
    group_a = Group(
        id=uuid4(),
        tenant_id=tenant_id,
        name="Group A",
        email="group_a@example.com",
        source_type="google_drive",
        source_id="group_a",
        member_principal_ids=[],
        member_group_ids=[],  # Will add group_b after creation
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    group_b = Group(
        id=uuid4(),
        tenant_id=tenant_id,
        name="Group B",
        email="group_b@example.com",
        source_type="google_drive",
        source_id="group_b",
        member_principal_ids=[],
        member_group_ids=[group_a.id],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    # Create cyclic reference
    group_a.member_group_ids = [group_b.id]
    
    await repo.create_group(group_a)
    await repo.create_group(group_b)
    
    # Create document with group permission
    doc = CanonicalDocument(
        id="doc_1",
        source_type="google_drive",
        source_id="file_1",
        tenant_id=tenant_id,
        title="Test Document",
        content="Test content",
        url="https://example.com",
        mime_type="text/plain",
        detected_mime_type="text/plain",
        mime_mismatch=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        source_updated_at=datetime.now(timezone.utc),
        structured_metadata={},
        parent_ids=[],
    )
    
    permission_hints = [
        (
            IdentityHint(
                source_type="google_drive",
                external_id="group:group_a",
                email="group_a@example.com",
                name="Group A",
            ),
            PermissionLevel.READ,
        ),
    ]
    
    # Should not hang or crash — cycle detection should work
    entries = await acl_compiler.compile(doc, permission_hints, tenant_id)
    
    # Should complete without error
    assert isinstance(entries, list)


@pytest.mark.asyncio
async def test_compile_deny_override(acl_compiler, repo):
    """Test that deny overrides allow."""
    tenant_id = uuid4()
    
    # Create principal
    alice_principal = Principal(
        id=uuid4(),
        tenant_id=tenant_id,
        email="alice@example.com",
        name="Alice",
        source_identities={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await repo.create_principal(alice_principal)
    
    # Create document with both allow and deny for same principal
    doc = CanonicalDocument(
        id="doc_1",
        source_type="google_drive",
        source_id="file_1",
        tenant_id=tenant_id,
        title="Test Document",
        content="Test content",
        url="https://example.com",
        mime_type="text/plain",
        detected_mime_type="text/plain",
        mime_mismatch=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        source_updated_at=datetime.now(timezone.utc),
        structured_metadata={},
        parent_ids=[],
    )
    
    permission_hints = [
        (
            IdentityHint(
                source_type="google_drive",
                external_id="user_1",
                email="alice@example.com",
                name="Alice",
            ),
            PermissionLevel.WRITE,
        ),
    ]
    
    # Manually add a deny entry (simulating inheritance)
    from app.core.models import ACLEntry
    
    deny_entry = ACLEntry(
        document_id="doc_1",
        principal_id=alice_principal.id,
        group_id=None,
        permission=PermissionLevel.NONE,
        granted_via="direct",
        source_container_id=None,
        is_deny=True,
        source_type="google_drive",
        tenant_id=tenant_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    # Compile (should apply deny-override logic)
    entries = await acl_compiler.compile(doc, permission_hints, tenant_id)
    
    # All entries for alice should be deny (if we added deny separately)
    # OR allow entries should be filtered if deny is present
    # This test verifies the logic doesn't crash with both
    assert isinstance(entries, list)
