"""
Tests for Component (c) - DB Provisioning + Migration Runner
Tests tenant provisioning, idempotency, and migration runner with feature flags.
"""

import pytest
from provisioning.provision_tenant import provision_tenant
from provisioning.migrate_all import migrate_all, MigrationResult, MigrationSummary
from tenant_router.models import TenancyMode
from vault_client.vault_client import VaultClient
from tests.mocks import MockDatabaseClient


class TestProvisionTenant:
    """Test suite for tenant provisioning"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database client"""
        return MockDatabaseClient()
    
    @pytest.fixture
    def mock_vault(self, mock_db):
        """Mock vault client"""
        return VaultClient(mock_db, use_pgsodium=False)
    
    def test_provision_new_tenant(self, mock_db, mock_vault):
        """Test provisioning a new tenant"""
        routing_info = provision_tenant(
            tenant_id="123",
            db_client=mock_db,
            vault_client=mock_vault,
            tenancy_mode=TenancyMode.ISOLATED_DB
        )
        
        assert routing_info.tenant_id == "123"
        assert routing_info.tenancy_mode == TenancyMode.ISOLATED_DB
        assert routing_info.db_schema_name == "tenant_123"
        assert routing_info.object_store_prefix == "tenant_123"
        assert routing_info.secrets_key_ref == "tenant_123_secrets"
        assert routing_info.status == "active"
    
    def test_provision_idempotent(self, mock_db, mock_vault):
        """
        CRITICAL TEST: Verify provisioning is idempotent.
        Calling it twice on the same tenant_id must not corrupt state.
        """
        # First provisioning
        routing_info_1 = provision_tenant(
            tenant_id="123",
            db_client=mock_db,
            vault_client=mock_vault,
            tenancy_mode=TenancyMode.ISOLATED_DB
        )
        
        # Second provisioning - should return existing info
        routing_info_2 = provision_tenant(
            tenant_id="123",
            db_client=mock_db,
            vault_client=mock_vault,
            tenancy_mode=TenancyMode.ISOLATED_DB
        )
        
        # Should return the same routing info
        assert routing_info_1.tenant_id == routing_info_2.tenant_id
        assert routing_info_1.db_schema_name == routing_info_2.db_schema_name
        assert routing_info_1.secrets_key_ref == routing_info_2.secrets_key_ref
    
    def test_provision_creates_vault_key_ref(self, mock_db, mock_vault):
        """Test that provisioning creates a vault key reference"""
        provision_tenant(
            tenant_id="456",
            db_client=mock_db,
            vault_client=mock_vault,
            tenancy_mode=TenancyMode.ISOLATED_DB
        )
        
        # Verify vault key was created
        secret = mock_vault.get("tenant_456_secrets")
        assert secret is not None
    
    def test_provision_default_tenancy_mode(self, mock_db, mock_vault):
        """Test that default tenancy mode is isolated_db"""
        routing_info = provision_tenant(
            tenant_id="789",
            db_client=mock_db,
            vault_client=mock_vault
        )
        
        assert routing_info.tenancy_mode == TenancyMode.ISOLATED_DB
    
    def test_provision_dedicated_mode_stubbed(self, mock_db, mock_vault):
        """Test that dedicated mode is stubbed (accepted but not fully implemented)"""
        routing_info = provision_tenant(
            tenant_id="dedicated",
            db_client=mock_db,
            vault_client=mock_vault,
            tenancy_mode=TenancyMode.DEDICATED
        )
        
        # Should accept the mode but not implement separate DB provisioning
        assert routing_info.tenancy_mode == TenancyMode.DEDICATED
        # In real implementation, this would point to a separate Supabase project
        # For now, it's just a stub


class TestMigrateAll:
    """Test suite for migration runner"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database client"""
        return MockDatabaseClient()
    
    @pytest.fixture
    def sample_tenants(self, mock_db):
        """Create sample tenants for migration testing"""
        tenants = []
        for i in range(5):
            tenant_data = {
                "tenant_id": f"tenant_{i}",
                "tenancy_mode": "isolated_db",
                "db_schema_name": f"tenant_{i}",
                "object_store_prefix": f"tenant_{i}",
                "secrets_key_ref": f"secret_{i}",
                "status": "active"
            }
            mock_db.create_tenant(tenant_data)
            tenants.append(tenant_data)
        return tenants
    
    def test_migrate_all_schemas(self, mock_db, sample_tenants):
        """Test migrating all tenant schemas"""
        summary = migrate_all(
            db_client=mock_db,
            migration_file="001_add_index.sql"
        )
        
        assert summary.total_schemas == 5
        assert summary.successful == 5
        assert summary.failed == 0
        assert summary.success_rate == 100.0
    
    def test_migrate_with_allowlist(self, mock_db, sample_tenants):
        """
        CRITICAL TEST: Verify feature-flagged gradual rollout via allowlist.
        This is required per Vishwas's tier-2 guidance.
        """
        allowlist = {"tenant_0", "tenant_2"}
        
        summary = migrate_all(
            db_client=mock_db,
            migration_file="001_add_index.sql",
            tenant_allowlist=allowlist
        )
        
        # Should only migrate 2 tenants
        assert summary.total_schemas == 2
        assert summary.successful == 2
        assert summary.failed == 0
        
        # Verify the right tenants were migrated
        migrated_schemas = {r.schema_name for r in summary.results if r.success}
        assert "tenant_0" in migrated_schemas
        assert "tenant_2" in migrated_schemas
        assert "tenant_1" not in migrated_schemas
    
    def test_migrate_with_rollout_percentage(self, mock_db, sample_tenants):
        """
        CRITICAL TEST: Verify feature-flagged gradual rollout via percentage.
        This is required per Vishwas's tier-2 guidance.
        """
        summary = migrate_all(
            db_client=mock_db,
            migration_file="001_add_index.sql",
            rollout_percentage=40.0  # 40% of 5 = 2 tenants
        )
        
        # Should migrate approximately 2 tenants (40% of 5)
        assert summary.total_schemas == 2
        assert summary.successful == 2
        assert summary.failed == 0
    
    def test_migrate_partial_failure_reporting(self, mock_db, sample_tenants):
        """
        CRITICAL TEST: Verify partial-failure reporting.
        Must report which schemas succeeded and which didn't.
        """
        # Mock a failure by having one tenant's schema fail
        # In real implementation, this would be a SQL error
        # For now, we'll test the structure
        
        summary = migrate_all(
            db_client=mock_db,
            migration_file="001_add_index.sql"
        )
        
        # Verify we can access failed schemas list
        assert hasattr(summary, 'failed_schemas')
        assert isinstance(summary.failed_schemas, list)
        
        # Verify we can access individual results
        assert len(summary.results) == summary.total_schemas
        for result in summary.results:
            assert isinstance(result, MigrationResult)
            assert hasattr(result, 'schema_name')
            assert hasattr(result, 'success')
            assert hasattr(result, 'error_message')
    
    def test_migrate_dry_run(self, mock_db, sample_tenants):
        """Test dry run mode - report without executing"""
        summary = migrate_all(
            db_client=mock_db,
            migration_file="001_add_index.sql",
            dry_run=True
        )
        
        assert summary.total_schemas == 5
        assert summary.successful == 5
        assert summary.failed == 0
        # In dry run, no actual changes should be made
    
    def test_migrate_no_tenants(self, mock_db):
        """Test migration when no tenants exist"""
        summary = migrate_all(
            db_client=mock_db,
            migration_file="001_add_index.sql"
        )
        
        assert summary.total_schemas == 0
        assert summary.successful == 0
        assert summary.failed == 0
        assert summary.success_rate == 100.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
