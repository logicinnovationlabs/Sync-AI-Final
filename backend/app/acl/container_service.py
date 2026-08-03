"""
Container service for managing folder hierarchies and container permissions.

Persists ContainerEdge and ContainerACLEntry rows.
Provides cycle-safe upward traversal for inheritance.
"""

import logging
from typing import List, Set, Optional
from uuid import UUID
from datetime import datetime, timezone

from app.core.models import ContainerEdge, ContainerACLEntry

logger = logging.getLogger(__name__)


class ContainerService:
    """
    Manages container hierarchy and direct container permissions.
    
    Provides cycle-safe ancestor traversal and caching for performance.
    """
    
    def __init__(self, canonical_repo, cache_ttl: int = 600):
        """
        Initialize container service.
        
        Args:
            canonical_repo: Repository for ContainerEdge and ContainerACLEntry persistence
            cache_ttl: TTL for cached ancestor chains (seconds)
        """
        self.repo = canonical_repo
        self.cache_ttl = cache_ttl
        self._ancestor_cache = {}  # {(tenant_id, container_id): [ancestor_ids]}
        self._cache_timestamps = {}
    
    async def get_ancestors(
        self, container_id: str, tenant_id: UUID, max_depth: int = 50
    ) -> List[str]:
        """
        Get ancestor containers in upward traversal order.
        
        Cycle-safe: tracks visited containers and stops on revisit.
        Max depth is a hard backstop even if cycle detection has a gap.
        
        Args:
            container_id: Starting container ID
            tenant_id: Tenant ID for scoping
            max_depth: Maximum traversal depth (default 50)
            
        Returns:
            List of ancestor container IDs (nearest to farthest)
        """
        # Check cache
        cache_key = (str(tenant_id), container_id)
        if cache_key in self._ancestor_cache:
            cache_time = self._cache_timestamps.get(cache_key, 0)
            if (datetime.now(timezone.utc).timestamp() - cache_time) < self.cache_ttl:
                return self._ancestor_cache[cache_key]
        
        # Traverse upward
        ancestors = []
        visited: Set[str] = set()
        current = container_id
        depth = 0
        
        while current and depth < max_depth:
            # Cycle detection
            if current in visited:
                logger.error(
                    f"Container cycle detected at {current} in tenant {tenant_id} "
                    f"(visited: {visited})"
                )
                break
            
            visited.add(current)
            
            # Get parent
            parent_id = await self.repo.get_parent_container(current, tenant_id)
            if not parent_id:
                break
            
            ancestors.append(parent_id)
            current = parent_id
            depth += 1
        
        # Max depth reached
        if depth >= max_depth:
            logger.error(
                f"Container traversal max depth ({max_depth}) reached for {container_id} "
                f"in tenant {tenant_id}"
            )
        
        # Cache result
        self._ancestor_cache[cache_key] = ancestors
        self._cache_timestamps[cache_key] = datetime.now(timezone.utc).timestamp()
        
        return ancestors
    
    async def get_container_permissions(
        self, container_id: str, tenant_id: UUID
    ) -> List[ContainerACLEntry]:
        """
        Get direct permissions set on a container.
        
        Args:
            container_id: Container ID
            tenant_id: Tenant ID for scoping
            
        Returns:
            List of ContainerACLEntry objects
        """
        return await self.repo.get_container_acl_entries(container_id, tenant_id)
    
    async def upsert_container_edge(
        self, parent_id: str, child_id: str, source_type: str, tenant_id: UUID
    ) -> None:
        """
        Create or update a container edge.
        
        Args:
            parent_id: Parent container ID
            child_id: Child container ID
            source_type: Source type identifier
            tenant_id: Tenant ID for scoping
        """
        edge = ContainerEdge(
            parent_container_id=parent_id,
            child_container_id=child_id,
            tenant_id=tenant_id,
            source_type=source_type,
            created_at=datetime.now(timezone.utc),
        )
        
        await self.repo.upsert_container_edge(edge)
        
        # Invalidate cache for this child
        cache_key = (str(tenant_id), child_id)
        self._ancestor_cache.pop(cache_key, None)
        self._cache_timestamps.pop(cache_key, None)
    
    async def upsert_container_acl(self, entry: ContainerACLEntry) -> None:
        """
        Create or update a container ACL entry.
        
        Args:
            entry: ContainerACLEntry to persist
        """
        await self.repo.upsert_container_acl(entry)
    
    def invalidate_cache(self, container_id: str, tenant_id: UUID) -> None:
        """
        Invalidate cached ancestor chain for a container.
        
        Called when container hierarchy changes.
        
        Args:
            container_id: Container ID
            tenant_id: Tenant ID
        """
        cache_key = (str(tenant_id), container_id)
        self._ancestor_cache.pop(cache_key, None)
        self._cache_timestamps.pop(cache_key, None)
