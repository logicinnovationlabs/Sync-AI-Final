"""
Unit tests for TenantResolver.
"""

import pytest
from uuid import uuid4

from app.services.tenant_resolver import tenant_resolver, TenantRouting
from app.core.exceptions import TenantNotFoundError
from app.models.tenant import Tenant
from app.storage.vault_client import MockVaultClient


@pytest.mark.asyncio
async def test_tenant_resolver_cache_miss_then_hit(test_db, test_redis, mock_vault):
    """Test tenant resolver with cache miss then cache hit."""
    tenant_id = uuid4()
    db_secret_key = f"kv/tenant-{tenant_id}/db_password"
    
    # Store password in mock Vault
    await mock_vault.set_secret(db_secret_key, "test_password")
    from app.storage.vault_client import vault_client
    await vault_client.set_secret(db_secret_key, "test_password")

    
    # Create tenant in control-plane DB
    tenant = Tenant(
        tenant_id=tenant_id,
        name="TestTenant",
        subdomain="testtenant",
        tenancy_mode="isolated_db",
        config={},
        db_host="localhost",
        db_name="testdb",
        db_user="testuser",
        db_secret_key=db_secret_key,
    )
    test_db.add(tenant)
    await test_db.commit()
    
    # First resolve (cache miss)
    routing = await tenant_resolver.resolve(str(tenant_id))
    
    assert routing.tenant_id == str(tenant_id)
    assert routing.db_host == "localhost"
    assert routing.db_password == "test_password"
    
    # Second resolve (cache hit - should be faster)
    routing2 = await tenant_resolver.resolve(str(tenant_id))
    
    assert routing2.tenant_id == routing.tenant_id
    assert routing2.db_password == routing.db_password

    from app.storage.redis_client import redis_client

    cached = await redis_client.get_json(str(tenant_id), "routing")
    assert cached is not None
    assert "db_password" not in cached
    assert cached.get("db_secret_key") == db_secret_key


@pytest.mark.asyncio
async def test_tenant_resolver_not_found():
    """Test tenant resolver with non-existent tenant."""
    fake_tenant_id = str(uuid4())
    
    with pytest.raises(TenantNotFoundError):
        await tenant_resolver.resolve(fake_tenant_id)
