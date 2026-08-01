"""
Tenant Router - Main implementation.
Single entry point for tenant routing resolution.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import logging

from .models import Tenant, TenantRoutingInfo, TenancyMode

logger = logging.getLogger(__name__)


class TenantRouter:
    """
    Tenant metadata lookup and routing service.
    
    Per-tenant cache with configurable TTL (default 45 min).
    Ensures tenant A's cache entry cannot be returned for tenant B.
    """
    
    def __init__(
        self,
        db_client,
        vault_client,
        cache_ttl_minutes: int = 45
    ):
        """
        Initialize TenantRouter.
        
        Args:
            db_client: Database client for querying tenants table
            vault_client: Vault client for resolving secrets_key_ref
            cache_ttl_minutes: TTL for per-tenant cache entries (default 45)
        """
        self.db_client = db_client
        self.vault_client = vault_client
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        
        # Per-tenant cache: Dict[tenant_id, (routing_info, expiry)]
        self._cache: Dict[str, Tuple[TenantRoutingInfo, datetime]] = {}
        
    def resolve(self, tenant_id: str) -> TenantRoutingInfo:
        """
        Resolve routing information for a tenant.
        
        This is the single entry point every other service call must go through.
        
        Args:
            tenant_id: The tenant identifier
            
        Returns:
            TenantRoutingInfo with schema name, resolved secret handle, object prefix
            
        Raises:
            ValueError: If tenant_id is not found
        """
        # Check cache first
        cached_entry = self._get_from_cache(tenant_id)
        if cached_entry:
            logger.debug(f"Cache hit for tenant {tenant_id}")
            return cached_entry
        
        # Cache miss - query database
        logger.debug(f"Cache miss for tenant {tenant_id}, querying database")
        tenant = self._fetch_tenant_from_db(tenant_id)
        
        # Resolve secret handle from vault
        resolved_secret = self._resolve_secret_handle(tenant.secrets_key_ref)
        
        # Build routing info
        routing_info = TenantRoutingInfo(
            tenant_id=tenant.tenant_id,
            tenancy_mode=tenant.tenancy_mode,
            db_schema_name=tenant.db_schema_name,
            object_store_prefix=tenant.object_store_prefix,
            secrets_key_ref=tenant.secrets_key_ref,
            resolved_secret_handle=resolved_secret,
            status=tenant.status
        )
        
        # Cache the result
        self._store_in_cache(tenant_id, routing_info)
        
        return routing_info
    
    def invalidate_cache(self, tenant_id: Optional[str] = None):
        """
        Invalidate cache for a specific tenant or all tenants.
        
        Args:
            tenant_id: Specific tenant to invalidate, or None for all
        """
        if tenant_id:
            if tenant_id in self._cache:
                del self._cache[tenant_id]
                logger.debug(f"Invalidated cache for tenant {tenant_id}")
        else:
            self._cache.clear()
            logger.debug("Invalidated all tenant cache entries")
    
    def _get_from_cache(self, tenant_id: str) -> Optional[TenantRoutingInfo]:
        """
        Retrieve from cache if entry exists and is not expired.
        
        Explicitly ensures tenant A's cache entry cannot be returned for tenant B
        by strict tenant_id key matching.
        """
        if tenant_id not in self._cache:
            return None
        
        routing_info, expiry = self._cache[tenant_id]
        
        if datetime.utcnow() > expiry:
            # Entry expired, remove it
            del self._cache[tenant_id]
            return None
        
        return routing_info
    
    def _store_in_cache(self, tenant_id: str, routing_info: TenantRoutingInfo):
        """Store routing info in cache with expiry."""
        expiry = datetime.utcnow() + self.cache_ttl
        self._cache[tenant_id] = (routing_info, expiry)
        logger.debug(f"Cached routing info for tenant {tenant_id} (expires at {expiry})")
    
    def _fetch_tenant_from_db(self, tenant_id: str) -> Tenant:
        """
        Fetch tenant row from database.
        
        Args:
            tenant_id: The tenant identifier
            
        Returns:
            Tenant object
            
        Raises:
            ValueError: If tenant_id is not found
        """
        query = """
            SELECT tenant_id, tenancy_mode, db_schema_name, 
                   object_store_prefix, secrets_key_ref, created_at, status
            FROM tenants
            WHERE tenant_id = %s
        """
        
        result = self.db_client.fetch_one(query, (tenant_id,))
        
        if not result:
            raise ValueError(f"Tenant {tenant_id} not found")
        
        return Tenant(
            tenant_id=result["tenant_id"],
            tenancy_mode=TenancyMode(result["tenancy_mode"]),
            db_schema_name=result["db_schema_name"],
            object_store_prefix=result["object_store_prefix"],
            secrets_key_ref=result["secrets_key_ref"],
            created_at=result["created_at"],
            status=result["status"]
        )
    
    def _resolve_secret_handle(self, secrets_key_ref: str) -> Optional[str]:
        """
        Resolve secret handle from vault client.
        
        Args:
            secrets_key_ref: The key reference from the tenants table
            
        Returns:
            Resolved secret handle (or None if not applicable)
        """
        try:
            return self.vault_client.get(secrets_key_ref)
        except Exception as e:
            logger.warning(f"Failed to resolve secret handle for {secrets_key_ref}: {e}")
            return None
