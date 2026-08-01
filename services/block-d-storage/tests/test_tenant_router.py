"""
Tests for Component (a) - Tenant Router
Tests basic functionality, cache isolation, and TTL behavior.
"""

import pytest
from datetime import datetime, timedelta
from tenant_router.tenant_router import TenantRouter
from tenant_router.models import TenancyMode
from tests.mocks import MockDatabaseClient, MockVaultClient


class TestTenantRouter:
    """Test suite for TenantRouter"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database client"""
        return MockDatabaseClient()
    
    @pytest.fixture
    def mock_vault(self):
        """Mock vault client"""
        return MockVaultClient()
    
    @pytest.fixture
    def router(self, mock_db, mock_vault):
        """TenantRouter instance with 45 minute TTL"""
        return TenantRouter(mock_db, mock_vault, cache_ttl_minutes=45)
    
    @pytest.fixture
    def sample_tenant(self):
        """Sample tenant data"""
        return {
            "tenant_id": "tenant_123",
            "tenancy_mode": "isolated_db",
            "db_schema_name": "tenant_123",
            "object_store_prefix": "tenant_123",
            "secrets_key_ref": "secret_key_tenant_123",
            "created_at": datetime.utcnow(),
            "status": "active"
        }
    
    def test_resolve_basic(self, router, mock_db, mock_vault, sample_tenant):
        """Test basic resolve functionality"""
        # Setup
        mock_db.create_tenant(sample_tenant)
        mock_vault.set("secret_key_tenant_123", "resolved_secret_value")
        
        # Execute
        routing_info = router.resolve("tenant_123")
        
        # Assert
        assert routing_info.tenant_id == "tenant_123"
        assert routing_info.tenancy_mode == TenancyMode.ISOLATED_DB
        assert routing_info.db_schema_name == "tenant_123"
        assert routing_info.object_store_prefix == "tenant_123"
        assert routing_info.secrets_key_ref == "secret_key_tenant_123"
        assert routing_info.resolved_secret_handle == "resolved_secret_value"
        assert routing_info.status == "active"
    
    def test_resolve_not_found(self, router):
        """Test resolve with non-existent tenant raises ValueError"""
        with pytest.raises(ValueError, match="Tenant .* not found"):
            router.resolve("nonexistent_tenant")
    
    def test_cache_hit(self, router, mock_db, mock_vault, sample_tenant):
        """Test that cache is hit on second call"""
        # Setup
        mock_db.create_tenant(sample_tenant)
        mock_vault.set("secret_key_tenant_123", "resolved_secret_value")
        
        # First call - should hit DB
        routing_info_1 = router.resolve("tenant_123")
        
        # Second call - should hit cache (DB not called again)
        routing_info_2 = router.resolve("tenant_123")
        
        # Assert same data returned
        assert routing_info_1.tenant_id == routing_info_2.tenant_id
        assert routing_info_1.db_schema_name == routing_info_2.db_schema_name
    
    def test_cache_isolation_tenant_a_b(self, router, mock_db, mock_vault):
        """
        CRITICAL TEST: Ensure tenant A's cache entry cannot be returned for tenant B.
        This is the per-tenant cache isolation requirement.
        """
        # Setup two tenants
        tenant_a = {
            "tenant_id": "tenant_a",
            "tenancy_mode": "isolated_db",
            "db_schema_name": "tenant_a",
            "object_store_prefix": "tenant_a",
            "secrets_key_ref": "secret_key_a",
            "created_at": datetime.utcnow(),
            "status": "active"
        }
        
        tenant_b = {
            "tenant_id": "tenant_b",
            "tenancy_mode": "isolated_db",
            "db_schema_name": "tenant_b",
            "object_store_prefix": "tenant_b",
            "secrets_key_ref": "secret_key_b",
            "created_at": datetime.utcnow(),
            "status": "active"
        }
        
        mock_db.create_tenant(tenant_a)
        mock_db.create_tenant(tenant_b)
        mock_vault.set("secret_key_a", "secret_a_value")
        mock_vault.set("secret_key_b", "secret_b_value")
        
        # Resolve tenant A
        routing_info_a = router.resolve("tenant_a")
        
        # Resolve tenant B
        routing_info_b = router.resolve("tenant_b")
        
        # Assert strict isolation
        assert routing_info_a.tenant_id == "tenant_a"
        assert routing_info_a.db_schema_name == "tenant_a"
        assert routing_info_a.resolved_secret_handle == "secret_a_value"
        
        assert routing_info_b.tenant_id == "tenant_b"
        assert routing_info_b.db_schema_name == "tenant_b"
        assert routing_info_b.resolved_secret_handle == "secret_b_value"
        
        # Verify cross-contamination does not happen
        assert routing_info_a.db_schema_name != routing_info_b.db_schema_name
        assert routing_info_a.resolved_secret_handle != routing_info_b.resolved_secret_handle
    
    def test_cache_expiry(self, mock_db, mock_vault, sample_tenant):
        """Test that cache entries expire after TTL"""
        # Setup router with 1 minute TTL for testing
        router = TenantRouter(mock_db, mock_vault, cache_ttl_minutes=1)
        mock_db.create_tenant(sample_tenant)
        mock_vault.set("secret_key_tenant_123", "resolved_secret_value")
        
        # First call - cache populated
        routing_info_1 = router.resolve("tenant_123")
        assert len(router._cache) == 1
        
        # Manually expire the cache entry by setting expiry in the past
        tenant_id = "tenant_123"
        routing_info, _ = router._cache[tenant_id]
        past_expiry = datetime.utcnow() - timedelta(minutes=1)
        router._cache[tenant_id] = (routing_info, past_expiry)
        
        # Second call - cache miss due to expiry
        routing_info_2 = router.resolve("tenant_123")
        
        # Should still return correct data (re-fetched from DB)
        assert routing_info_2.tenant_id == "tenant_123"
    
    def test_invalidate_cache_specific_tenant(self, router, mock_db, mock_vault, sample_tenant):
        """Test cache invalidation for specific tenant"""
        # Setup
        mock_db.create_tenant(sample_tenant)
        mock_vault.set("secret_key_tenant_123", "resolved_secret_value")
        
        # Populate cache
        router.resolve("tenant_123")
        assert len(router._cache) == 1
        
        # Invalidate specific tenant
        router.invalidate_cache("tenant_123")
        assert len(router._cache) == 0
    
    def test_invalidate_cache_all(self, router, mock_db, mock_vault):
        """Test cache invalidation for all tenants"""
        # Setup multiple tenants
        for i in range(3):
            tenant_data = {
                "tenant_id": f"tenant_{i}",
                "tenancy_mode": "isolated_db",
                "db_schema_name": f"tenant_{i}",
                "object_store_prefix": f"tenant_{i}",
                "secrets_key_ref": f"secret_key_{i}",
                "created_at": datetime.utcnow(),
                "status": "active"
            }
            mock_db.create_tenant(tenant_data)
            mock_vault.set(f"secret_key_{i}", f"secret_value_{i}")
        
        # Populate cache for all
        for i in range(3):
            router.resolve(f"tenant_{i}")
        
        assert len(router._cache) == 3
        
        # Invalidate all
        router.invalidate_cache()
        assert len(router._cache) == 0
    
    def test_vault_resolution_failure(self, router, mock_db, sample_tenant):
        """Test that vault resolution failure is handled gracefully"""
        # Setup tenant but no vault secret
        mock_db.create_tenant(sample_tenant)
        # Don't set vault secret - will fail gracefully
        
        # Should still return routing info with None secret handle
        routing_info = router.resolve("tenant_123")
        assert routing_info.tenant_id == "tenant_123"
        assert routing_info.resolved_secret_handle is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
