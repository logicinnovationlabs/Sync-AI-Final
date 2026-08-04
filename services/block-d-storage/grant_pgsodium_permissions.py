"""
Grant EXECUTE privilege on pgsodium functions to postgres user.
"""

import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from encryption.db_client import DatabaseClient

def main():
    print("Granting pgsodium function permissions to postgres...")
    
    block_d_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(block_d_dir, '.env')
    load_dotenv(env_path, override=True)
    
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    
    if not db_url:
        print("ERROR: Database connection string not found")
        return False
    
    db_client = DatabaseClient(db_url)
    
    try:
        # Grant EXECUTE on all pgsodium functions
        print("\n1. Granting EXECUTE on all pgsodium functions to postgres...")
        db_client.execute("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pgsodium TO postgres")
        print("   ✓ Grant executed")
        
        # Set default privileges for future functions
        print("\n2. Setting default privileges for future pgsodium functions...")
        db_client.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA pgsodium GRANT EXECUTE ON FUNCTIONS TO postgres")
        print("   ✓ Default privileges set")
        
        # Verify the grant worked
        print("\n3. Verifying crypto_aead_det_encrypt privilege...")
        result = db_client.fetch_one("""
            SELECT has_function_privilege(
                current_user, 
                'pgsodium.crypto_aead_det_encrypt(bytea, bytea, uuid)', 
                'EXECUTE'
            ) as has_priv
        """)
        print(f"   Has EXECUTE privilege: {result.has_priv}")
        
        if result.has_priv:
            print("\n✓ Permissions granted successfully")
            return True
        else:
            print("\n✗ Permission grant failed")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db_client.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
