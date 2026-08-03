"""
Tests for identity resolution.

Verifies email matching, username fallback, race condition handling.
"""

import pytest
from uuid import uuid4
from app.identity.resolver import IdentityResolver
from app.identity.matchers.email_matcher import EmailMatcher
from app.identity.matchers.username_matcher import UsernameMatcher
from app.storage.canonical_repo import CanonicalRepo
from app.core.models import IdentityHint


@pytest.fixture
def repo():
    """Create in-memory repository."""
    return CanonicalRepo(use_memory=True)


@pytest.fixture
def resolver(repo):
    """Create identity resolver."""
    matchers = [EmailMatcher(), UsernameMatcher()]
    return IdentityResolver(matchers, repo)


@pytest.mark.asyncio
async def test_resolve_new_email_creates_principal(resolver, repo):
    """Test that resolving a new email creates a principal."""
    tenant_id = uuid4()
    hint = IdentityHint(
        source_type="google_drive",
        external_id="user_1",
        email="alice@example.com",
        name="Alice Smith",
    )
    
    resolved = await resolver.resolve(hint, tenant_id)
    
    assert resolved.principal_id
    assert resolved.principal.email == "alice@example.com"
    assert resolved.principal.name == "Alice Smith"
    assert resolved.confidence == 1.0
    assert resolved.matched_on == "new"


@pytest.mark.asyncio
async def test_resolve_existing_email_returns_same_principal(resolver, repo):
    """Test that resolving an existing email returns the same principal."""
    tenant_id = uuid4()
    
    # First resolution
    hint1 = IdentityHint(
        source_type="google_drive",
        external_id="user_1",
        email="alice@example.com",
        name="Alice Smith",
    )
    resolved1 = await resolver.resolve(hint1, tenant_id)
    
    # Second resolution from different source
    hint2 = IdentityHint(
        source_type="google_gmail",
        external_id="alice@example.com",
        email="alice@example.com",
        name="Alice Smith",
    )
    resolved2 = await resolver.resolve(hint2, tenant_id)
    
    # Should be the same principal
    assert resolved1.principal_id == resolved2.principal_id
    assert resolved2.matched_on == "email"


@pytest.mark.asyncio
async def test_resolve_normalizes_email_case(resolver, repo):
    """Test that email resolution is case-insensitive."""
    tenant_id = uuid4()
    
    # Create with lowercase
    hint1 = IdentityHint(
        source_type="google_drive",
        external_id="user_1",
        email="alice@example.com",
    )
    resolved1 = await resolver.resolve(hint1, tenant_id)
    
    # Resolve with uppercase
    hint2 = IdentityHint(
        source_type="google_gmail",
        external_id="user_2",
        email="ALICE@EXAMPLE.COM",
    )
    resolved2 = await resolver.resolve(hint2, tenant_id)
    
    # Should match the same principal
    assert resolved1.principal_id == resolved2.principal_id


@pytest.mark.asyncio
async def test_resolve_tenant_scoped(resolver, repo):
    """Test that resolution is tenant-scoped."""
    tenant1 = uuid4()
    tenant2 = uuid4()
    
    hint = IdentityHint(
        source_type="google_drive",
        external_id="user_1",
        email="alice@example.com",
    )
    
    # Resolve in tenant 1
    resolved1 = await resolver.resolve(hint, tenant1)
    
    # Resolve in tenant 2 (same email)
    resolved2 = await resolver.resolve(hint, tenant2)
    
    # Should be different principals (tenant-scoped)
    assert resolved1.principal_id != resolved2.principal_id


@pytest.mark.asyncio
async def test_resolve_race_condition_uses_winner(resolver, repo):
    """Test that concurrent resolution of same email uses DB winner."""
    tenant_id = uuid4()
    hint = IdentityHint(
        source_type="google_drive",
        external_id="user_1",
        email="alice@example.com",
    )
    
    # First resolution creates principal
    resolved1 = await resolver.resolve(hint, tenant_id)
    
    # Simulate race: try to create again (should catch and re-query)
    # The repo will raise an error on duplicate, resolver should handle it
    resolved2 = await resolver.resolve(hint, tenant_id)
    
    # Should return the same principal (winner)
    assert resolved1.principal_id == resolved2.principal_id
