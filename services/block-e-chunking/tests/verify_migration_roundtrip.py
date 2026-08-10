"""
Round-trip migration verification per v7.0 §2.3.

Tests that migration 002 preserves data through column renames:
1. Insert test data with old schema (before migration 002)
2. Run migration 002 (upgrade)
3. Verify data preserved after column renames
4. Run migration 002 (downgrade)
5. Verify data preserved after downgrade
6. Run migration 002 (upgrade again)
7. Verify data preserved after re-upgrade
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override DATABASE_URL to use localhost for testing
os.environ['DATABASE_URL'] = 'postgresql://postgres:postgres@localhost:5432/block_e'

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.models.chunk_record import ChunkRecord

# Use sync database URL
SYNC_DATABASE_URL = os.environ['DATABASE_URL'].replace('postgresql+asyncpg://', 'postgresql://')
db_engine = create_engine(SYNC_DATABASE_URL, echo=False)
SessionLocal = sessionmaker(db_engine, expire_on_commit=False)


def test_migration_roundtrip():
    """Test migration 002 preserves data through column renames."""
    
    print("=" * 80)
    print("MIGRATION ROUND-TRIP VERIFICATION (v7.0 §2.3)")
    print("=" * 80)
    
    session = SessionLocal()
    
    try:
        # Clean up any existing test data
        print("\n[0] Cleaning up existing test data...")
        session.execute(text("DELETE FROM chunk_records WHERE chunk_id LIKE 'test_migration_%'"))
        session.execute(text("DELETE FROM embedding_jobs WHERE job_id LIKE 'test_migration_%'"))
        session.commit()
        print("   ✓ Test data cleaned up")
        
        # Get current migration version
        print("\n[1] Checking current migration version...")
        result = session.execute(text("SELECT version_num FROM alembic_version"))
        current_version = result.scalar()
        print(f"   Current migration version: {current_version}")
        
        # If already at version 002, downgrade to 001 first
        if current_version == '002':
            print("\n[2] Downgrading to migration 001 to start fresh...")
            session.close()
            import subprocess
            subprocess.run(['python', '-m', 'alembic', 'downgrade', '-1'], 
                         cwd='d:\\PROJECTS\\Sync Ai Final\\services\\block-e-chunking',
                         check=True, capture_output=True)
            session = SessionLocal()
            print("   ✓ Downgraded to migration 001")
        
        # Insert test data with OLD schema (before migration 002)
        # Migration 002 renames: content_text -> chunk_text, source_span_start -> start_byte, source_span_end -> end_byte
        print("\n[3] Inserting test data with OLD schema (before migration 002)...")
        session.execute(text("""
            INSERT INTO chunk_records (
                chunk_id, tenant_id, document_id, document_version, chunk_index, chunk_type,
                content_text, token_count, source_span_start, source_span_end,
                chunker_version, content_hash, chunk_content_checksum, source_run_id
            ) VALUES (
                'test_migration_001', 'test_tenant', 'test_doc', 1, 0, 'file_summary',
                'test content before migration', 5, 0, 12,
                '1.0.0', 'abc123', 'def456', 'test_run_001'
            )
        """))
        session.commit()
        print("   ✓ Test data inserted with old column names")
        
        # Verify data was inserted with old column names
        print("\n[4] Verifying data with old column names...")
        result = session.execute(text("""
            SELECT content_text, source_span_start, source_span_end 
            FROM chunk_records 
            WHERE chunk_id = 'test_migration_001'
        """))
        row = result.fetchone()
        if row:
            print(f"   ✓ Old columns exist: content_text='{row[0]}', start={row[1]}, end={row[2]}")
        else:
            print("   ✗ Failed to insert test data with old schema")
            return False
        
        # Run migration 002 (upgrade)
        print("\n[5] Running migration 002 (upgrade)...")
        session.close()
        import subprocess
        result = subprocess.run(['python', '-m', 'alembic', 'upgrade', 'head'], 
                              cwd='d:\\PROJECTS\\Sync Ai Final\\services\\block-e-chunking',
                              check=True, capture_output=True, text=True)
        print(f"   ✓ Migration upgrade completed")
        print(f"   Output: {result.stdout[-200:]}")
        
        session = SessionLocal()
        
        # Verify data preserved after upgrade with NEW column names
        print("\n[6] Verifying data preserved after upgrade with NEW column names...")
        result = session.execute(text("""
            SELECT chunk_text, start_byte, end_byte 
            FROM chunk_records 
            WHERE chunk_id = 'test_migration_001'
        """))
        row = result.fetchone()
        if row:
            print(f"   ✓ New columns exist: chunk_text='{row[0]}', start={row[1]}, end={row[2]}")
            if row[0] == 'test content before migration':
                print("   ✓ Data preserved through column rename")
            else:
                print("   ✗ Data NOT preserved through column rename")
                return False
        else:
            print("   ✗ Data lost after migration")
            return False
        
        # Verify old columns no longer exist
        print("\n[7] Verifying old columns no longer exist...")
        try:
            result = session.execute(text("""
                SELECT content_text FROM chunk_records WHERE chunk_id = 'test_migration_001'
            """))
            print("   ✗ Old column content_text still exists (should have been renamed)")
            return False
        except Exception as e:
            print("   ✓ Old column content_text no longer exists (correctly renamed)")
        
        # Run migration 002 (downgrade)
        print("\n[8] Running migration 002 (downgrade)...")
        session.close()
        result = subprocess.run(['python', '-m', 'alembic', 'downgrade', '-1'], 
                              cwd='d:\\PROJECTS\\Sync Ai Final\\services\\block-e-chunking',
                              check=True, capture_output=True, text=True)
        print(f"   ✓ Migration downgrade completed")
        print(f"   Output: {result.stdout[-200:]}")
        
        session = SessionLocal()
        
        # Verify data preserved after downgrade with OLD column names
        print("\n[9] Verifying data preserved after downgrade with OLD column names...")
        result = session.execute(text("""
            SELECT content_text, source_span_start, source_span_end 
            FROM chunk_records 
            WHERE chunk_id = 'test_migration_001'
        """))
        row = result.fetchone()
        if row:
            print(f"   ✓ Old columns restored: content_text='{row[0]}', start={row[1]}, end={row[2]}")
            if row[0] == 'test content before migration':
                print("   ✓ Data preserved through downgrade")
            else:
                print("   ✗ Data NOT preserved through downgrade")
                return False
        else:
            print("   ✗ Data lost after downgrade")
            return False
        
        # Run migration 002 (upgrade again)
        print("\n[10] Running migration 002 (upgrade again)...")
        session.close()
        result = subprocess.run(['python', '-m', 'alembic', 'upgrade', 'head'], 
                              cwd='d:\\PROJECTS\\Sync Ai Final\\services\\block-e-chunking',
                              check=True, capture_output=True, text=True)
        print(f"   ✓ Migration upgrade completed")
        
        session = SessionLocal()
        
        # Verify data preserved after re-upgrade
        print("\n[11] Verifying data preserved after re-upgrade...")
        result = session.execute(text("""
            SELECT chunk_text, start_byte, end_byte 
            FROM chunk_records 
            WHERE chunk_id = 'test_migration_001'
        """))
        row = result.fetchone()
        if row:
            print(f"   ✓ New columns exist: chunk_text='{row[0]}', start={row[1]}, end={row[2]}")
            if row[0] == 'test content before migration':
                print("   ✓ Data preserved through re-upgrade")
            else:
                print("   ✗ Data NOT preserved through re-upgrade")
                return False
        else:
            print("   ✗ Data lost after re-upgrade")
            return False
        
        print("\n" + "=" * 80)
        print("MIGRATION ROUND-TRIP VERIFICATION: PASSED")
        print("=" * 80)
        print("\nEVIDENCE:")
        print("- Data inserted with old schema (content_text, source_span_start/end)")
        print("- Data preserved through migration 002 upgrade (renamed to chunk_text, start_byte/end_byte)")
        print("- Data preserved through migration 002 downgrade (restored to old names)")
        print("- Data preserved through migration 002 re-upgrade (renamed again)")
        print("- Column renames are reversible and data-safe")
        
        return True
        
    finally:
        # Clean up test data
        session.execute(text("DELETE FROM chunk_records WHERE chunk_id LIKE 'test_migration_%'"))
        session.execute(text("DELETE FROM embedding_jobs WHERE job_id LIKE 'test_migration_%'"))
        session.commit()
        session.close()


if __name__ == "__main__":
    try:
        success = test_migration_roundtrip()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
