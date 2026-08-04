"""
Check what Vault functions and tables actually exist in the database.
"""

import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from encryption.db_client import DatabaseClient

def main():
    print("Checking Vault extension functions and tables...")
    
    block_d_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(block_d_dir, '.env')
    load_dotenv(env_path, override=True)
    
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    
    if not db_url:
        print("ERROR: Database connection string not found")
        return False
    
    db_client = DatabaseClient(db_url)
    
    try:
        # Check if vault extension exists
        print("\n1. Checking vault extension:")
        result = db_client.fetch_one("SELECT 1 FROM pg_extension WHERE extname = 'vault'")
        if result:
            print("   ✓ vault extension is enabled")
        else:
            print("   ✗ vault extension is NOT enabled")
            return False
        
        # Check vault schema tables
        print("\n2. Checking vault schema tables:")
        tables = db_client.fetch_all("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'vault'
            ORDER BY table_name
        """)
        for table in tables:
            print(f"   - {table.table_name}")
        
        # Check vault functions
        print("\n3. Checking vault functions:")
        functions = db_client.fetch_all("""
            SELECT proname, pg_get_function_arguments(oid) as args
            FROM pg_proc 
            WHERE pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'vault')
            ORDER BY proname
        """)
        for func in functions:
            print(f"   - {func.proname}({func.args})")
        
        # Check vault.secrets structure
        print("\n4. Checking vault.secrets structure:")
        columns = db_client.fetch_all("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'vault' AND table_name = 'secrets'
            ORDER BY ordinal_position
        """)
        for col in columns:
            print(f"   - {col.column_name}: {col.data_type}")
        
        # Check if vault.decrypted_secrets view exists
        print("\n5. Checking vault.decrypted_secrets view:")
        result = db_client.fetch_one("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.views 
                WHERE table_schema = 'vault' AND table_name = 'decrypted_secrets'
            ) as exists
        """)
        if result.exists:
            print("   ✓ vault.decrypted_secrets view exists")
            # Check its structure
            columns = db_client.fetch_all("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = 'vault' AND table_name = 'decrypted_secrets'
                ORDER BY ordinal_position
            """)
            for col in columns:
                print(f"     - {col.column_name}: {col.data_type}")
        else:
            print("   ✗ vault.decrypted_secrets view does NOT exist")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db_client.close()
    
    return True

if __name__ == "__main__":
    main()
