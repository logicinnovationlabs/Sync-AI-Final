"""
Tests for container service.

Verifies cycle-safe ancestor traversal and container permission handling.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from app.acl.container_service import ContainerService
from app.storage.canonical_repo import CanonicalRepo
from app.core.models import ContainerACLEntry, PermissionLevel


@pytest.fixture
def repo():
    """Create in-memory repository."""
    return CanonicalRepo(use_memory=True)


@pytest.fixture
def container_service(repo):
    """Create container service."""
    return ContainerService(repo, cache_ttl=60)


@pytest.mark.asyncio
async def test_get_ancestors_simple_hierarchy(container_service, repo):
    """Test ancestor traversal in simple hierarchy."""
    tenant_id = uuid4()
    
    # Create hierarchy: root -> folder_a -> folder_b -> folder_c
    from app.core.models import ContainerEdge
    
    edge1 = ContainerEdge(
        parent_container_id="root",
        child_container_id="folder_a",
        tenant_id=tenant_id,
        source_type="google_drive",
        created_at=datetime.now(timezone.utc),
    )
    edge2 = ContainerEdge(
        parent_container_id="folder_a",
        child_container_id="folder_b",
        tenant_id=tenant_id,
        source_type="google_drive",
        created_at=datetime.now(timezone.utc),
    )
    edge3 = ContainerEdge(
        parent_container_id="folder_b",
        child_container_id="folder_c",
        tenant_id=tenant_id,
        source_type="google_drive",
        created_at=datetime.now(timezone.utc),
    )
    
    await repo.upsert_container_edge(edge1)
    await repo.upsert_container_edge(edge2)
    await repo.upsert_container_edge(edge3)
    
    # Get ancestors of folder_c
    ancestors = await container_service.get_ancestors("folder_c", tenant_id)
    
    # Should be [folder_b, folder_a, root] (nearest to farthest)
    assert ancestors == ["folder_b", "folder_a", "root"]


@pytest.mark.asyncio
async def test_get_ancestors_detects_cycle(container_service, repo):
    """Test that ancestor traversal detects and stops on cycles."""
    tenant_id = uuid4()
    
    # Create cycle: cycle_a -> cycle_b -> cycle_c -> cycle_a
    from app.core.models import ContainerEdge
    
    edge1 = ContainerEdge(
        parent_container_id="cycle_b",
        child_container_id="cycle_a",
        tenant_id=tenant_id,
        source_type="google_drive",
        created_at=datetime.now(timezone.utc),
    )
    edge2 = ContainerEdge(
        parent_container_id="cycle_c",
        child_container_id="cycle_b",
        tenant_id=tenant_id,
        source_type="google_drive",
        created_at=datetime.now(timezone.utc),
    )
    edge3 = ContainerEdge(
        parent_container_id="cycle_a",
        child_container_id="cycle_c",
        tenant_id=tenant_id,
        source_type="google_drive",
        created_at=datetime.now(timezone.utc),
    )
    
    await repo.upsert_container_edge(edge1)
    await repo.upsert_container_edge(edge2)
    await repo.upsert_container_edge(edge3)
    
    # Get ancestors of cycle_a (should detect cycle and stop)
    ancestors = await container_service.get_ancestors("cycle_a", tenant_id, max_depth=10)
    
    # Should terminate early (not hang), returning partial result
    # The exact result depends on where cycle is detected
    assert len(ancestors) < 10  # Should not reach max_depth


@pytest.mark.asyncio
async def test_get_container_permissions(container_service, repo):
    """Test retrieval of container permissions."""
    tenant_id = uuid4()
    principal_id = uuid4()
    
    # Create container ACL entry
    entry = ContainerACLEntry(
        container_id="folder_a",
        principal_id=principal_id,
        group_id=None,
        permission=PermissionLevel.WRITE,
        is_deny=False,
        source_type="google_drive",
        tenant_id=tenant_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await repo.upsert_container_acl(entry)
    
    # Get permissions
    perms = await container_service.get_container_permissions("folder_a", tenant_id)
    
    assert len(perms) == 1
    assert perms[0].container_id == "folder_a"
    assert perms[0].principal_id == principal_id
    assert perms[0].permission == PermissionLevel.WRITE


@pytest.mark.asyncio
async def test_cache_invalidation(container_service, repo):
    """Test that cache is invalidated when hierarchy changes."""
    tenant_id = uuid4()
    
    # Create initial hierarchy
    from app.core.models import ContainerEdge
    
    edge = ContainerEdge(
        parent_container_id="parent_a",
        child_container_id="child_a",
        tenant_id=tenant_id,
        source_type="google_drive",
        created_at=datetime.now(timezone.utc),
    )
    await repo.upsert_container_edge(edge)
    
    # Get ancestors (populates cache)
    ancestors1 = await container_service.get_ancestors("child_a", tenant_id)
    assert ancestors1 == ["parent_a"]
    
    # Change parent
    edge2 = ContainerEdge(
        parent_container_id="parent_b",
        child_container_id="child_a",
        tenant_id=tenant_id,
        source_type="google_drive",
        created_at=datetime.now(timezone.utc),
    )
    await container_service.upsert_container_edge("parent_b", "child_a", "google_drive", tenant_id)
    
    # Get ancestors again (should reflect change)
    ancestors2 = await container_service.get_ancestors("child_a", tenant_id)
    assert ancestors2 == ["parent_b"]
