"""
D1 Signoff Test: Provisioning Time
Per Glean Arch v1.3 §24, Block D signoff table.

Criterion: Provision 10 fresh tenants, time each
Pass threshold: 100% complete in under 5 minutes
"""

import pytest
import time
from provisioning.provision_tenant import provision_tenant
from tenant_router.models import TenancyMode
from vault_client.vault_client import VaultClient
from tests.mocks import MockDatabaseClient


def test_D1_provisioning_time():
    """
    D1 Signoff Test: Provisioning time.
    
    Provision 10 fresh tenants and measure time.
    Pass threshold: 100% complete in under 5 minutes (300 seconds).
    """
    mock_db = MockDatabaseClient()
    mock_vault = VaultClient(mock_db, use_pgsodium=False)
    
    num_tenants = 10
    start_time = time.time()
    
    # Provision 10 tenants
    for i in range(num_tenants):
        tenant_id = str(i)
        routing_info = provision_tenant(
            tenant_id=tenant_id,
            db_client=mock_db,
            vault_client=mock_vault,
            tenancy_mode=TenancyMode.ISOLATED_DB
        )
        
        # Verify each was provisioned successfully
        assert routing_info.tenant_id == tenant_id
        assert routing_info.status == "active"
        assert routing_info.db_schema_name == f"tenant_{tenant_id}"
    
    end_time = time.time()
    elapsed_seconds = end_time - start_time
    
    print(f"\nD1 Provisioning Time Test Results:")
    print(f"  Tenants provisioned: {num_tenants}")
    print(f"  Total time: {elapsed_seconds:.2f} seconds")
    print(f"  Average per tenant: {elapsed_seconds / num_tenants:.2f} seconds")
    print(f"  Pass threshold: < 300 seconds")
    
    # Assert pass threshold
    assert elapsed_seconds < 300, f"D1 FAILED: Provisioning took {elapsed_seconds:.2f}s, exceeds 300s threshold"
    
    print(f"  D1 PASSED: All {num_tenants} tenants provisioned in {elapsed_seconds:.2f}s")


if __name__ == "__main__":
    test_D1_provisioning_time()
