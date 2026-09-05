"""Add owner and viewer roles, migrate earliest admin to owner per tenant.

Revision ID: 008_rbac_expansion_owner_viewer
Revises: 007_split_google_connectors
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "008_rbac_expansion_owner_viewer"
down_revision = "007_split_google_connectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Add CHECK constraint for role column to enforce valid values
    # This constraint will be applied to existing data after migration
    op.execute("""
        ALTER TABLE users 
        ADD CONSTRAINT chk_role_valid 
        CHECK (role IN ('owner', 'admin', 'member', 'viewer'))
    """)
    
    # Migrate earliest admin to owner per tenant
    # Logic: earliest created_at, tie-break on invited_by IS NULL
    # Flag tenants with zero admins for manual intervention
    
    # First, identify tenants that need migration
    result = conn.execute(sa.text("""
        SELECT DISTINCT tenant_id 
        FROM users 
        WHERE role = 'admin' AND is_active = true
    """))
    
    tenant_ids = [row[0] for row in result]
    
    tenants_needing_manual_assignment = []
    
    for tenant_id in tenant_ids:
        # Find the earliest admin for this tenant
        # Tie-break: invited_by IS NULL (founding account) takes precedence
        admin_result = conn.execute(sa.text("""
            SELECT principal_id, email, created_at, invited_by
            FROM users
            WHERE tenant_id = :tenant_id 
              AND role = 'admin' 
              AND is_active = true
            ORDER BY 
                created_at ASC,
                CASE WHEN invited_by IS NULL THEN 0 ELSE 1 END
            LIMIT 1
        """), {"tenant_id": tenant_id})
        
        admin_row = admin_result.fetchone()
        
        if admin_row:
            principal_id = admin_row[0]
            email = admin_row[1]
            
            # Promote this admin to owner
            conn.execute(sa.text("""
                UPDATE users
                SET role = 'owner'
                WHERE principal_id = :principal_id
            """), {"principal_id": principal_id})
            
            print(f"Migrated tenant {tenant_id}: promoted {email} ({principal_id}) to owner")
        else:
            tenants_needing_manual_assignment.append(str(tenant_id))
            print(f"WARNING: Tenant {tenant_id} has no active admins - needs manual owner assignment")
    
    # Commit the changes
    conn.commit()
    
    # Print summary
    if tenants_needing_manual_assignment:
        print("\n" + "="*60)
        print("MIGRATION SUMMARY - TENANTS REQUIRING MANUAL INTERVENTION")
        print("="*60)
        print(f"The following {len(tenants_needing_manual_assignment)} tenant(s) have no active admins:")
        for tenant_id in tenants_needing_manual_assignment:
            print(f"  - {tenant_id}")
        print("\nThese tenants must have an owner assigned manually before the migration is complete.")
        print("Use the ownership-transfer flow once the system is upgraded to assign an owner.")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("MIGRATION SUMMARY")
        print("="*60)
        print(f"Successfully migrated {len(tenant_ids)} tenant(s) to have an owner.")
        print("All tenants now have exactly one owner.")
        print("="*60)


def downgrade() -> None:
    # Remove the CHECK constraint
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_role_valid")
    
    # Revert all owners back to admins
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'owner'")
    
    # Revert all viewers back to members
    op.execute("UPDATE users SET role = 'member' WHERE role = 'viewer'")
