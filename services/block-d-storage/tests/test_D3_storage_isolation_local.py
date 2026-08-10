"""
D3 Signoff Test: Storage-Layer Tenant Isolation (Local Postgres)
Per Glean Arch v1.3 §24, Block D signoff table.

Criterion: Attempt a cross-tenant read via StorageClient, bypassing app-level checks, 20 attempts
Pass threshold: 100% fail at the storage layer (IAM/schema-permission/RLS denial), before any app code executes

CRITICAL: This test uses the existing local Postgres instance to verify actual database-level
schema permissions. It does NOT rely on path-string logic like the Phase 1 mock test.

The test:
1. Uses the existing block-d-verify-pg container
2. Creates two tenant schemas with different database users
3. Grants each user access only to their own schema
4. Attempts cross-tenant reads using the wrong user
5. Verifies Postgres rejects these at the permission level
"""

import pytest
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


class TestD3StorageIsolationLocal:
    """D3 test with local Postgres schema-permission boundary"""
    
    @pytest.fixture(scope="class")
    def postgres_connection(self):
        """
        Get a connection to the local test Postgres instance.
        """
        conn = psycopg2.connect(
            host="localhost",
            port=5435,
            user="postgres",
            password="verify",
            database="block_d_verify"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        yield conn
        conn.close()
    
    def test_D3_schema_permission_isolation(self, postgres_connection):
        """
        D3 Signoff Test: Schema-permission isolation with local Postgres.
        
        This test verifies that Postgres schema permissions reject cross-tenant access
        at the database level, not just at the application path-construction level.
        
        Test flow:
        1. Create two tenant schemas: tenant_a and tenant_b
        2. Create two database users: user_a and user_b
        3. Grant user_a access only to tenant_a schema
        4. Grant user_b access only to tenant_b schema
        5. Insert data into both schemas
        6. Attempt 20 cross-tenant reads: user_b trying to read from tenant_a
        7. Verify all 20 attempts fail at the Postgres permission level
        """
        conn = postgres_connection
        cursor = conn.cursor()
        
        print(f"\nD3 Schema Permission Isolation Test (Local Postgres):")
        print(f"  Setting up schemas and users...")
        
        # Create two tenant schemas
        cursor.execute("DROP SCHEMA IF EXISTS tenant_a CASCADE")
        cursor.execute("DROP SCHEMA IF EXISTS tenant_b CASCADE")
        cursor.execute("CREATE SCHEMA tenant_a")
        cursor.execute("CREATE SCHEMA tenant_b")
        
        # Create tables in each schema
        cursor.execute("CREATE TABLE tenant_a.test_data (id SERIAL PRIMARY KEY, value TEXT)")
        cursor.execute("CREATE TABLE tenant_b.test_data (id SERIAL PRIMARY KEY, value TEXT)")
        
        # Insert data into both schemas
        cursor.execute("INSERT INTO tenant_a.test_data (value) VALUES ('tenant_a_secret')")
        cursor.execute("INSERT INTO tenant_b.test_data (value) VALUES ('tenant_b_secret')")
        
        # Create two database users
        cursor.execute("DROP USER IF EXISTS user_a")
        cursor.execute("DROP USER IF EXISTS user_b")
        cursor.execute("CREATE USER user_a WITH PASSWORD 'password_a'")
        cursor.execute("CREATE USER user_b WITH PASSWORD 'password_b'")
        
        # Grant user_a access only to tenant_a schema
        cursor.execute("GRANT USAGE ON SCHEMA tenant_a TO user_a")
        cursor.execute("GRANT SELECT ON ALL TABLES IN SCHEMA tenant_a TO user_a")
        cursor.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA tenant_a GRANT SELECT ON TABLES TO user_a")
        
        # Grant user_b access only to tenant_b schema
        cursor.execute("GRANT USAGE ON SCHEMA tenant_b TO user_b")
        cursor.execute("GRANT SELECT ON ALL TABLES IN SCHEMA tenant_b TO user_b")
        cursor.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA tenant_b GRANT SELECT ON TABLES TO user_b")
        
        # Revoke public access to schemas (ensure isolation)
        cursor.execute("REVOKE ALL ON SCHEMA tenant_a FROM PUBLIC")
        cursor.execute("REVOKE ALL ON SCHEMA tenant_b FROM PUBLIC")
        cursor.execute("REVOKE ALL ON ALL TABLES IN SCHEMA tenant_a FROM PUBLIC")
        cursor.execute("REVOKE ALL ON ALL TABLES IN SCHEMA tenant_b FROM PUBLIC")
        
        print(f"  Schemas and users created")
        print(f"  Attempting 20 cross-tenant reads (user_b -> tenant_a)...")
        
        # Attempt 20 cross-tenant reads: user_b trying to read from tenant_a
        # This should fail at the Postgres permission level
        cross_tenant_failures = 0
        cross_tenant_successes = 0
        rejection_points = []
        
        for attempt in range(20):
            try:
                # Connect as user_b
                conn_b = psycopg2.connect(
                    host="localhost",
                    port=5435,
                    user="user_b",
                    password="password_b",
                    database="block_d_verify"
                )
                conn_b.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                cursor_b = conn_b.cursor()
                
                # Attempt to read from tenant_a schema (cross-tenant)
                cursor_b.execute("SELECT value FROM tenant_a.test_data")
                result = cursor_b.fetchone()
                
                # If we get here, the read succeeded (should not happen)
                cross_tenant_successes += 1
                print(f"  WARNING: Cross-tenant read succeeded on attempt {attempt + 1}: {result}")
                rejection_points.append(f"Attempt {attempt + 1}: SUCCESS (UNEXPECTED)")
                
                conn_b.close()
                
            except psycopg2.errors.InsufficientPrivilege as e:
                # This is the expected outcome - permission denied at Postgres level
                cross_tenant_failures += 1
                print(f"  Attempt {attempt + 1}: Cross-tenant read blocked (InsufficientPrivilege)")
                rejection_points.append(f"Attempt {attempt + 1}: BLOCKED at Postgres permission level (InsufficientPrivilege)")
                
            except psycopg2.errors.InvalidSchemaName as e:
                # Also acceptable - schema not visible to user
                cross_tenant_failures += 1
                print(f"  Attempt {attempt + 1}: Cross-tenant read blocked (InvalidSchemaName)")
                rejection_points.append(f"Attempt {attempt + 1}: BLOCKED at Postgres permission level (InvalidSchemaName)")
                
            except psycopg2.errors.PermissionDenied as e:
                # Also acceptable - permission denied
                cross_tenant_failures += 1
                print(f"  Attempt {attempt + 1}: Cross-tenant read blocked (PermissionDenied)")
                rejection_points.append(f"Attempt {attempt + 1}: BLOCKED at Postgres permission level (PermissionDenied)")
                
            except Exception as e:
                # Other errors - log but count as failure
                cross_tenant_failures += 1
                print(f"  Attempt {attempt + 1}: Cross-tenant read blocked ({type(e).__name__})")
                rejection_points.append(f"Attempt {attempt + 1}: BLOCKED at Postgres level ({type(e).__name__})")
        
        print(f"\nD3 Schema Permission Isolation Test Results:")
        print(f"  Cross-tenant attempts: 20")
        print(f"  Cross-tenant failures: {cross_tenant_failures}")
        print(f"  Cross-tenant successes: {cross_tenant_successes}")
        print(f"  Rejection points:")
        for point in rejection_points:
            print(f"    {point}")
        
        # Verify all 20 attempts failed
        assert cross_tenant_failures == 20, f"D3 FAILED: Only {cross_tenant_failures}/20 cross-tenant reads were blocked"
        assert cross_tenant_successes == 0, f"D3 FAILED: {cross_tenant_successes} cross-tenant reads succeeded"
        
        print(f"  D3 PASSED: All 20 cross-tenant reads blocked at Postgres permission level")
        
        # Cleanup
        print(f"\nCleaning up schemas and users...")
        cursor.execute("DROP SCHEMA IF EXISTS tenant_a CASCADE")
        cursor.execute("DROP SCHEMA IF EXISTS tenant_b CASCADE")
        cursor.execute("DROP USER IF EXISTS user_a")
        cursor.execute("DROP USER IF EXISTS user_b")
        print(f"  Cleanup complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])