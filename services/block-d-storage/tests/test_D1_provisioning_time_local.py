"""
D1 Signoff Test: Provisioning Time (Local Postgres)
Per Glean Arch v1.3 §24, Block D signoff table.

Criterion: Provision 10 fresh tenants, time each
Pass threshold: 100% complete in under 5 minutes

This test runs against the local Postgres container for fresh verification.
"""

import pytest
import os
import time
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from provisioning.provision_tenant import provision_tenant
from tenant_router.models import TenancyMode
from vault_client.vault_client import VaultClient
from encryption.db_client import DatabaseClient


class TestD1ProvisioningTimeLocal:
    """D1 test with local Postgres container."""
    
    @pytest.fixture(scope="class")
    def db_connection_string(self):
        """
        Local Postgres connection string.
        """
        db_url = "postgresql://postgres:verify@localhost:5435/block_d_verify"
        
        print(f"\nD1 Test Configuration:")
        print(f"  Database host: localhost")
        print(f"  Database port: 5435")
        print(f"  Database name: block_d_verify")
        print(f"  Connection loaded: True")
        
        return db_url
    
    @pytest.fixture(scope="class")
    def db_client(self, db_connection_string):
        """
        Create database client for test setup/teardown.
        """
        client = DatabaseClient(db_connection_string)
        yield client
        client.close()
    
    @pytest.fixture(scope="class")
    def vault_client(self, db_client):
        """
        Create vault client with real database connection.
        Using TableVaultBackend with pgcrypto.
        """
        return VaultClient(db_client, use_pgsodium=False)
    
    @pytest.fixture(scope="class")
    def tenants_table_setup(self, db_client):
        """
        Create the tenants table and secrets table if they don't exist.
        This is required for provisioning tests.
        """
        print(f"\nD1: Setting up tables...")
        
        # Create tenants table
        db_client.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id VARCHAR(255) PRIMARY KEY,
                tenancy_mode VARCHAR(50) NOT NULL,
                db_schema_name VARCHAR(255) NOT NULL,
                object_store_prefix VARCHAR(255) NOT NULL,
                secrets_key_ref VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(50) DEFAULT 'active'
            );
            
            COMMENT ON TABLE tenants IS 'Tenant metadata table - secrets_key_ref is a vault key name pointer, never a raw secret';
            COMMENT ON COLUMN tenants.secrets_key_ref IS 'Vault key reference (pointer), never a raw password or connection string';
        """, ())
        
        # Create secrets table for TableVaultBackend
        db_client.execute("""
            CREATE TABLE IF NOT EXISTS secrets (
                key_ref VARCHAR(255) PRIMARY KEY,
                value_jsonb JSONB NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            
            COMMENT ON TABLE secrets IS 'Vault secrets table - stores credential envelopes as JSONB';
            COMMENT ON COLUMN secrets.value_jsonb IS 'Credential envelope (opaque JSONB), never raw secrets';
        """, ())
        
        print(f"D1: Tables created/verified")
        
        yield True
        
        # Cleanup: Drop test tenant rows and secrets
        print(f"\nD1: Cleaning up test data...")
        for i in range(10):
            tenant_id = f"d1_test_tenant_{i}"
            try:
                db_client.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant_id,))
                db_client.execute("DELETE FROM secrets WHERE key_ref = %s", (f"tenant_{tenant_id}_secrets",))
            except Exception:
                pass
    
    def test_D1_provisioning_time_local(self, db_client, vault_client, tenants_table_setup):
        """
        D1 Signoff Test: Provisioning time with local Postgres.
        
        Provision 10 fresh tenants and measure actual time.
        Pass threshold: 100% complete in under 5 minutes (300 seconds).
        """
        print(f"\nD1 Provisioning Time Test (Local Postgres):")
        
        num_tenants = 10
        per_tenant_times = []
        start_time = time.time()
        
        # Provision 10 tenants
        for i in range(num_tenants):
            tenant_id = f"d1_test_tenant_{i}"
            tenant_start = time.time()
            
            try:
                routing_info = provision_tenant(
                    tenant_id=tenant_id,
                    db_client=db_client,
                    vault_client=vault_client,
                    tenancy_mode=TenancyMode.ISOLATED_DB
                )
                
                # Verify each was provisioned successfully
                assert routing_info.tenant_id == tenant_id
                assert routing_info.status == "active"
                assert routing_info.db_schema_name == f"tenant_{tenant_id}"
                
                tenant_elapsed = time.time() - tenant_start
                per_tenant_times.append(tenant_elapsed)
                print(f"  Tenant {tenant_id} provisioned successfully in {tenant_elapsed:.3f}s")
                
            except Exception as e:
                print(f"  ERROR: Failed to provision tenant {tenant_id}: {e}")
                raise
        
        end_time = time.time()
        elapsed_seconds = end_time - start_time
        
        print(f"\nD1 Provisioning Time Test Results:")
        print(f"  Tenants provisioned: {num_tenants}")
        print(f"  Total time: {elapsed_seconds:.2f} seconds")
        print(f"  Average per tenant: {elapsed_seconds / num_tenants:.2f} seconds")
        print(f"  Per-tenant times:")
        for i, t in enumerate(per_tenant_times):
            print(f"    Tenant {i}: {t:.3f}s")
        print(f"  Pass threshold: < 300 seconds")
        
        # Assert pass threshold
        assert elapsed_seconds < 300, f"D1 FAILED: Provisioning took {elapsed_seconds:.2f}s, exceeds 300s threshold"
        
        print(f"  D1 PASSED: All {num_tenants} tenants provisioned in {elapsed_seconds:.2f}s")
        
        # Cleanup: Drop test schemas
        print(f"\nCleaning up test schemas...")
        for i in range(num_tenants):
            tenant_id = f"d1_test_tenant_{i}"
            schema_name = f"tenant_{tenant_id}"
            try:
                db_client.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE", ())
                db_client.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant_id,))
                print(f"  Cleaned up {tenant_id}")
            except Exception as e:
                print(f"  WARNING: Failed to cleanup {tenant_id}: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])