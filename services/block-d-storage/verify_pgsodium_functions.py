"""
Check pgsodium crypto_aead_det_encrypt/decrypt function signatures.
"""

import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from encryption.db_client import DatabaseClient

def main():
    print("Checking pgsodium crypto_aead_det functions...")
    
    block_d_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(block_d_dir, '.env')
    load_dotenv(env_path, override=True)
    
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    
    if not db_url:
        print("ERROR: Database connection string not found")
        return False
    
    db_client = DatabaseClient(db_url)
    
    try:
        # Check function signatures
        print("\n1. Checking pgsodium.crypto_aead_det_encrypt signature:")
        result = db_client.fetch_one("""
            SELECT pg_get_function_arguments(oid) as args
            FROM pg_proc 
            WHERE proname = 'crypto_aead_det_encrypt' 
            AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'pgsodium')
        """)
        if result:
            print(f"   Arguments: {result.args}")
        
        print("\n2. Checking pgsodium.crypto_aead_det_decrypt signature:")
        result = db_client.fetch_one("""
            SELECT pg_get_function_arguments(oid) as args
            FROM pg_proc 
            WHERE proname = 'crypto_aead_det_decrypt' 
            AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'pgsodium')
        """)
        if result:
            print(f"   Arguments: {result.args}")
        
        print("\n3. Checking pgsodium.crypto_aead_det_encrypt return type:")
        result = db_client.fetch_one("""
            SELECT pg_get_function_result(oid) as result_type
            FROM pg_proc 
            WHERE proname = 'crypto_aead_det_encrypt' 
            AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'pgsodium')
        """)
        if result:
            print(f"   Return type: {result.result_type}")
            
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
