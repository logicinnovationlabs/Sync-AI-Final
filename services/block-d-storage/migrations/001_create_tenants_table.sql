-- Migration 001: Create tenants table
-- This is the central table for tenant metadata in Block D

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id VARCHAR(255) PRIMARY KEY,
    tenancy_mode VARCHAR(50) NOT NULL CHECK (tenancy_mode IN ('pooled', 'isolated_db', 'dedicated')),
    db_schema_name VARCHAR(255) NOT NULL,
    object_store_prefix VARCHAR(255) NOT NULL,
    secrets_key_ref VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted'))
);

-- Index for common lookup patterns
CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);
CREATE INDEX IF NOT EXISTS idx_tenants_tenancy_mode ON tenants(tenancy_mode);

-- Comment explaining the architecture decision
COMMENT ON TABLE tenants IS 'Tenant metadata table per Glean Arch v1.3 §24 Block D. Never stores raw connection strings or passwords - uses secrets_key_ref to vault.';
COMMENT ON COLUMN tenants.tenancy_mode IS 'Three values: pooled (not implemented), isolated_db (default, one schema per tenant), dedicated (stubbed, separate DB instance)';
COMMENT ON COLUMN tenants.secrets_key_ref IS 'Reference to vault key, not the secret itself. Resolved through VaultClient.';
