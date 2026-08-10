-- ACL post-check schema for Block J (acl_entries)
CREATE TABLE IF NOT EXISTS acl_entries (
    id BIGSERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL,
    principal_id TEXT,
    group_id TEXT,
    permission_type TEXT NOT NULL DEFAULT 'read',
    is_deny BOOLEAN NOT NULL DEFAULT FALSE,
    tenant_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_acl_entries_tenant_doc
    ON acl_entries (tenant_id, doc_id);

CREATE INDEX IF NOT EXISTS idx_acl_entries_principal
    ON acl_entries (tenant_id, principal_id);

CREATE INDEX IF NOT EXISTS idx_acl_entries_group
    ON acl_entries (tenant_id, group_id);
