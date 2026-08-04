"""
D2 Signoff Test: Backup/Restore Integrity (Local Postgres)
Per Glean Arch v1.3 §24, Block D signoff table.

Criterion: Backup a non-prod tenant, drop it, restore it
Pass threshold: Row/object counts and checksums match pre-backup state exactly

This test runs against the local Postgres container for fresh verification.
"""

import pytest
import os
import hashlib
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backup_cli.backup_restore import backup_tenant, restore_tenant
from provisioning.provision_tenant import provision_tenant
from tenant_router.models import TenancyMode
from vault_client.vault_client import VaultClient
from encryption.db_client import DatabaseClient


class TestD2BackupRestoreLocal:
    """D2 test with local Postgres container."""
    
    @pytest.fixture(scope="class")
    def db_connection_string(self):
        """
        Local Postgres connection string.
        """
        db_url = "postgresql://postgres:verify@localhost:5435/block_d_verify"
        
        print(f"\nD2 Test Configuration:")
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
    def tables_setup(self, db_client):
        """
        Create the tenants table and secrets table if they don't exist.
        This is required for backup/restore tests.
        """
        print(f"\nD2: Setting up tables...")
        
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
        
        print(f"D2: Tables created/verified")
        
        yield True
        
        # Cleanup
        print(f"\nD2: Cleaning up test data...")
        try:
            schema_name = "tenant_d2_test_tenant"
            db_client.execute(f"DROP TABLE IF EXISTS {schema_name}.test_data CASCADE", ())
            db_client.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE", ())
            db_client.execute("DELETE FROM tenants WHERE tenant_id = %s", ("d2_test_tenant",))
            db_client.execute("DELETE FROM secrets WHERE key_ref = %s", ("tenant_d2_test_tenant_secrets",))
            # Clear in-memory backup stores
            from backup_cli.backup_restore import _backup_metadata_store, _backup_data_store
            _backup_metadata_store.clear()
            _backup_data_store.clear()
        except Exception:
            pass
    
    @pytest.fixture(scope="class")
    def test_tenant_setup(self, db_client, vault_client, tables_setup):
        """
        Create a test tenant with sample data for backup/restore testing.
        """
        tenant_id = "d2_test_tenant"
        
        print(f"\nD2 Test Tenant Setup:")
        print(f"  Creating tenant: {tenant_id}")
        
        # Provision the tenant
        routing_info = provision_tenant(
            tenant_id=tenant_id,
            db_client=db_client,
            vault_client=vault_client,
            tenancy_mode=TenancyMode.ISOLATED_DB
        )
        
        schema_name = f"tenant_{tenant_id}"
        
        # Clean up any existing test data
        try:
            db_client.execute(f"DROP TABLE IF EXISTS {schema_name}.test_data CASCADE", ())
        except Exception:
            pass
        
        # Create a test table with sample data
        print(f"  Creating test table with sample data")
        db_client.execute(f"""
            CREATE TABLE {schema_name}.test_data (
                id SERIAL PRIMARY KEY,
                name TEXT,
                value TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """, ())
        
        # Insert sample data
        for i in range(100):
            db_client.execute(f"""
                INSERT INTO {schema_name}.test_data (name, value)
                VALUES (%s, %s)
            """, (f"item_{i}", f"value_{i}"))
        
        # Get initial row count
        initial_count_result = db_client.fetch_one(f"SELECT COUNT(*) as count FROM {schema_name}.test_data", ())
        initial_row_count = initial_count_result['count'] if initial_count_result else 0
        
        # Calculate pre-backup checksum (normalized JSON)
        all_data = db_client.fetch_all(f"SELECT * FROM {schema_name}.test_data ORDER BY id", ())
        pre_backup_data = [row.to_dict() for row in all_data]
        import json
        pre_backup_normalized = json.dumps(pre_backup_data, sort_keys=True, default=str)
        pre_backup_checksum = hashlib.sha256(pre_backup_normalized.encode()).hexdigest()
        
        print(f"  Initial row count: {initial_row_count}")
        print(f"  Pre-backup checksum: {pre_backup_checksum}")
        
        yield {
            "tenant_id": tenant_id,
            "schema_name": schema_name,
            "initial_row_count": initial_row_count,
            "pre_backup_checksum": pre_backup_checksum
        }
        
        # Cleanup
        print(f"\nD2 Test Tenant Cleanup:")
        print(f"  Dropping schema: {schema_name}")
        try:
            db_client.execute(f"DROP TABLE IF EXISTS {schema_name}.test_data CASCADE", ())
        except Exception:
            pass
        db_client.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE", ())
        db_client.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant_id,))
    
    def test_D2_backup_restore_integrity_local(self, db_client, test_tenant_setup):
        """
        D2 Signoff Test: Backup/restore integrity with local Postgres.
        
        Backup a non-prod tenant, drop its schema, restore it.
        Verify row counts and checksums match pre-backup state exactly.
        """
        tenant_id = test_tenant_setup["tenant_id"]
        schema_name = test_tenant_setup["schema_name"]
        initial_row_count = test_tenant_setup["initial_row_count"]
        pre_backup_checksum = test_tenant_setup["pre_backup_checksum"]
        
        print(f"\nD2 Backup/Restore Integrity Test (Local Postgres):")
        print(f"  Tenant ID: {tenant_id}")
        print(f"  Schema: {schema_name}")
        print(f"  Initial row count: {initial_row_count}")
        print(f"  Pre-backup checksum: {pre_backup_checksum}")
        
        # Step 1: Backup the tenant
        print(f"\n  Step 1: Backing up tenant...")
        backup_metadata = backup_tenant(db_client, tenant_id)
        
        print(f"    Backup ID: {backup_metadata.backup_id}")
        print(f"    Backup row count: {backup_metadata.row_count}")
        print(f"    Backup checksum: {backup_metadata.checksum}")
        
        # Verify backup captured the data
        assert backup_metadata.tenant_id == tenant_id
        assert backup_metadata.schema_name == schema_name
        assert backup_metadata.row_count >= initial_row_count, "Backup row count should be at least initial row count"
        
        # Step 2: Drop the schema
        print(f"\n  Step 2: Dropping schema...")
        db_client.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE", ())
        print(f"    Schema dropped")
        
        # Verify schema is gone
        check_result = db_client.fetch_one(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s",
            (schema_name,)
        )
        assert check_result is None, "Schema should be dropped"
        
        # Step 3: Restore the tenant
        print(f"\n  Step 3: Restoring tenant...")
        restore_metadata = restore_tenant(db_client, tenant_id, backup_metadata.backup_id)
        
        print(f"    Restore tenant ID: {restore_metadata.tenant_id}")
        print(f"    Restore schema: {restore_metadata.schema_name}")
        print(f"    Restore row count: {restore_metadata.row_count}")
        
        # Verify restore succeeded
        assert restore_metadata.tenant_id == tenant_id
        assert restore_metadata.schema_name == schema_name
        assert restore_metadata.row_count == backup_metadata.row_count, "Restore row count should match backup row count"
        
        # Step 4: Verify post-restore row count
        print(f"\n  Step 4: Verifying post-restore row count...")
        post_restore_count_result = db_client.fetch_one(f"SELECT COUNT(*) as count FROM {schema_name}.test_data", ())
        post_restore_row_count = post_restore_count_result['count'] if post_restore_count_result else 0
        
        print(f"    Post-restore row count: {post_restore_row_count}")
        assert post_restore_row_count == initial_row_count, f"Post-restore row count {post_restore_row_count} should match initial {initial_row_count}"
        
        # Step 5: Verify post-restore checksum
        print(f"\n  Step 5: Verifying post-restore checksum...")
        all_data = db_client.fetch_all(f"SELECT * FROM {schema_name}.test_data ORDER BY id", ())
        post_restore_data = [row.to_dict() for row in all_data]
        import json
        post_restore_normalized = json.dumps(post_restore_data, sort_keys=True, default=str)
        post_restore_checksum = hashlib.sha256(post_restore_normalized.encode()).hexdigest()
        
        print(f"    Post-restore checksum: {post_restore_checksum}")
        assert post_restore_checksum == pre_backup_checksum, f"Post-restore checksum should match pre-backup checksum"
        
        print(f"\nD2 Backup/Restore Integrity Test Results:")
        print(f"  Initial row count: {initial_row_count}")
        print(f"  Backup row count: {backup_metadata.row_count}")
        print(f"  Restored row count: {post_restore_row_count}")
        print(f"  Pre-backup checksum: {pre_backup_checksum}")
        print(f"  Post-restore checksum: {post_restore_checksum}")
        print(f"  Checksums match: True")
        print(f"  D2 PASSED: Row counts and checksums match pre-backup state exactly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])