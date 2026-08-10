"""
Check database user permissions for pgsodium functions.
"""

import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from encryption.db_client import DatabaseClient

def main():
    print("Checking database user and pgsodium permissions...")
    
    block_d_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(block_d_dir, '.env')
    load_dotenv(env_path, override=True)
    
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    
    if not db_url:
        print("ERROR: Database connection string not found")
        return False
    
    db_client = DatabaseClient(db_url)
    
    try:
        # Check current user
        print("\n1. Current database user:")
        result = db_client.fetch_one("SELECT current_user")
        print(f"   Current user: {result.current_user}")
        
        # Check if user is superuser
        print("\n2. Superuser check:")
        result = db_client.fetch_one("SELECT current_setting('is_superuser', true)")
        print(f"   Is superuser: {result.current_setting}")
        
        # Check pgsodium function permissions
        print("\n3. Checking pgsodium.crypto_aead_det_encrypt permissions:")
        try:
            result = db_client.fetch_one("""
                SELECT has_function_privilege(
                    current_user, 
                    'pgsodium.crypto_aead_det_encrypt(bytea, bytea, uuid)', 
                    'EXECUTE'
                ) as has_priv
            """)
            print(f"   Has EXECUTE privilege: {result.has_priv}")
        except Exception as e:
            print(f"   Error checking privilege: {e}")
        
        # Check all pgsodium functions
        print("\n4. All pgsodium functions:")
        functions = db_client.fetch_all("""
            SELECT proname, pg_get_function_arguments(oid) as args
            FROM pg_proc 
            WHERE pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'pgsodium')
            ORDER BY proname
            LIMIT 20
        """)
        for func in functions:
            print(f"   {func.proname}({func.args})")
            
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
