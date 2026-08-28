"""
Block C smoke test.

Quick sanity check that all Block C components are wired correctly.
"""

import pytest
from uuid import uuid4


def test_normalizer_strategies_registered():
    """Test that normalizer strategies are properly registered."""
    from app.normalizer.registry import normalizer_registry
    import app.normalizer.strategies
    
    # Should have google_drive and google_gmail registered
    drive_strategy = normalizer_registry.get("google_drive")
    assert drive_strategy.get_source_type() == "google_drive"
    
    gmail_strategy = normalizer_registry.get("google_gmail")
    assert gmail_strategy.get_source_type() == "google_gmail"
    
    # Should have fallback for unknown types
    unknown_strategy = normalizer_registry.get("unknown_source")
    assert unknown_strategy.get_source_type() == "generic"


def test_pipeline_initialization():
    """Test that pipeline can be initialized without errors."""
    from app.services.pipeline import Pipeline
    from app.normalizer.registry import normalizer_registry
    from app.identity.resolver import IdentityResolver
    from app.identity.matchers.email_matcher import EmailMatcher
    from app.identity.matchers.username_matcher import UsernameMatcher
    from app.acl.compiler import ACLCompiler
    from app.acl.container_service import ContainerService
    from app.storage.canonical_repo import CanonicalRepo
    
    # Initialize components
    canonical_repo = CanonicalRepo(use_memory=True)
    matchers = [EmailMatcher(), UsernameMatcher()]
    identity_resolver = IdentityResolver(matchers, canonical_repo)
    container_service = ContainerService(canonical_repo)
    acl_compiler = ACLCompiler(identity_resolver, container_service, canonical_repo)
    
    # Initialize pipeline
    pipeline = Pipeline(
        normalizer_registry,
        identity_resolver,
        acl_compiler,
        canonical_repo,
    )
    
    assert pipeline is not None
    assert pipeline.normalizer_registry is not None
    assert pipeline.identity_resolver is not None
    assert pipeline.acl_compiler is not None
    assert pipeline.canonical_repo is not None


@pytest.mark.asyncio
async def test_end_to_end_drive_document():
    """End-to-end smoke test: Drive document through full pipeline."""
    from app.services.pipeline import Pipeline
    from app.normalizer.registry import normalizer_registry
    from app.identity.resolver import IdentityResolver
    from app.identity.matchers.email_matcher import EmailMatcher
    from app.identity.matchers.username_matcher import UsernameMatcher
    from app.acl.compiler import ACLCompiler
    from app.acl.container_service import ContainerService
    from app.storage.canonical_repo import CanonicalRepo
    
    # Setup
    canonical_repo = CanonicalRepo(use_memory=True)
    matchers = [EmailMatcher(), UsernameMatcher()]
    identity_resolver = IdentityResolver(matchers, canonical_repo)
    container_service = ContainerService(canonical_repo)
    acl_compiler = ACLCompiler(identity_resolver, container_service, canonical_repo)
    
    pipeline = Pipeline(
        normalizer_registry,
        identity_resolver,
        acl_compiler,
        canonical_repo,
    )
    
    # Test document
    tenant_id = uuid4()
    canonical_repo.register_login_user(tenant_id, "test@example.com", uuid4())
    raw = {
        "id": "smoke_test_file",
        "name": "Smoke Test Document",
        "mimeType": "text/plain",
        "owners": [{"emailAddress": "test@example.com"}],
        "permissions": [
            {"type": "user", "emailAddress": "test@example.com", "role": "owner", "id": "perm_1"}
        ],
        "parents": [],
        "createdTime": "2024-01-01T00:00:00Z",
        "modifiedTime": "2024-01-01T00:00:00Z",
        "_test_extracted_text": "Smoke test content",
    }
    
    # Process
    result = await pipeline.process_raw(raw, "google_drive", tenant_id)
    
    # Verify
    assert result["canonical_document"] is not None
    assert result["canonical_document"].id == "google_drive_smoke_test_file"
    assert result["canonical_document"].title == "Smoke Test Document"
    
    assert result["acl_entries"] is not None
    assert len(result["acl_entries"]) >= 1
    
    assert result["unified_document"] is not None
    assert result["unified_document"].id == "smoke_test_file"
    assert len(result["unified_document"].permissions) >= 1


@pytest.mark.asyncio
async def test_end_to_end_gmail_message():
    """End-to-end smoke test: Gmail message through full pipeline."""
    from app.services.pipeline import Pipeline
    from app.normalizer.registry import normalizer_registry
    from app.identity.resolver import IdentityResolver
    from app.identity.matchers.email_matcher import EmailMatcher
    from app.identity.matchers.username_matcher import UsernameMatcher
    from app.acl.compiler import ACLCompiler
    from app.acl.container_service import ContainerService
    from app.storage.canonical_repo import CanonicalRepo
    
    # Setup
    canonical_repo = CanonicalRepo(use_memory=True)
    matchers = [EmailMatcher(), UsernameMatcher()]
    identity_resolver = IdentityResolver(matchers, canonical_repo)
    container_service = ContainerService(canonical_repo)
    acl_compiler = ACLCompiler(identity_resolver, container_service, canonical_repo)
    
    pipeline = Pipeline(
        normalizer_registry,
        identity_resolver,
        acl_compiler,
        canonical_repo,
    )
    
    # Test message
    tenant_id = uuid4()
    canonical_repo.register_login_user(tenant_id, "mailbox@example.com", uuid4())
    raw = {
        "id": "smoke_test_msg",
        "threadId": "thread_smoke",
        "labelIds": ["INBOX"],
        "snippet": "Smoke test snippet",
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Subject", "value": "Smoke Test Email"},
                {"name": "Delivered-To", "value": "mailbox@example.com"},
            ],
        },
        "internalDate": "1704067200000",
        "sizeEstimate": 1024,
        "_mailbox_email": "mailbox@example.com",
        "_test_extracted_text": "Smoke test email body",
    }
    
    # Process
    result = await pipeline.process_raw(raw, "google_gmail", tenant_id)
    
    # Verify
    assert result["canonical_document"] is not None
    assert result["canonical_document"].id == "google_gmail_smoke_test_msg"
    assert result["canonical_document"].title == "Smoke Test Email"
    
    assert result["acl_entries"] is not None
    assert len(result["acl_entries"]) >= 1
    
    assert result["unified_document"] is not None
    assert result["unified_document"].id == "smoke_test_msg"


def test_all_models_importable():
    """Smoke test: all Block C models are importable."""
    from app.core.models import (
        PermissionLevel,
        CanonicalDocument,
        Principal,
        Group,
        ACLEntry,
        ContainerACLEntry,
        ContainerEdge,
        IdentityHint,
        ResolvedIdentity,
    )
    
    # Just verify they're all importable
    assert PermissionLevel is not None
    assert CanonicalDocument is not None
    assert Principal is not None
    assert Group is not None
    assert ACLEntry is not None
    assert ContainerACLEntry is not None
    assert ContainerEdge is not None
    assert IdentityHint is not None
    assert ResolvedIdentity is not None
