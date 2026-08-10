"""
Component 1 Verification: Real Key Creation
Verifies that create_key() actually creates a key in pgsodium's store.
"""

import os
import sys
import time
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from encryption.encryption_client import EncryptionClient
from encryption.db_client import DatabaseClient

def main():
    print("=" * 60)
    print("Component 1 Verification: Real Key Creation")
    print("=" * 60)
    
    # Load environment
    block_d_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(block_d_dir, '.env')
    load_dotenv(env_path, override=True)
    
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    
    if not db_url:
        print("ERROR: Database connection string not found in environment")
        print("Please set SUPABASE_DB_URL, DATABASE_URL, or POSTGRES_URL in .env file")
        return False
    
    print(f"\n1. Connecting to database...")
    db_client = DatabaseClient(db_url)
    
    try:
        print("   Connected successfully")
        
        # Create EncryptionClient
        print(f"\n2. Creating EncryptionClient...")
        encryption_client = EncryptionClient(db_client)
        print("   EncryptionClient created successfully")
        
        # Create a key
        print(f"\n3. Creating new key via create_key()...")
        key_name = f"component1_test_key_{int(time.time())}"
        
        # Debug: check what's in pgsodium.decrypted_key before creation
        before_count = db_client.fetch_one("SELECT COUNT(*) as cnt FROM pgsodium.decrypted_key")
        print(f"   Keys before creation: {before_count.cnt if hasattr(before_count, 'cnt') else before_count}")
        
        # Debug: check table structure
        table_structure = db_client.fetch_all("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'pgsodium' AND table_name = 'decrypted_key'
            ORDER BY ordinal_position
        """)
        print(f"   pgsodium.decrypted_key structure:")
        for col in table_structure:
            print(f"     {col.column_name}: {col.data_type}")
        
        key_uuid = encryption_client.create_key(key_name=key_name)
        print(f"   Key created with UUID: {key_uuid}")
        
        # Verify the key exists in pgsodium.decrypted_key
        print(f"\n4. Querying pgsodium.decrypted_key to verify key exists...")
        result = db_client.fetch_one(
            """
            SELECT id, key_type, status, name 
            FROM pgsodium.decrypted_key 
            WHERE id = %s
            """,
            (key_uuid,)
        )
        
        if result:
            print(f"   Key found in pgsodium.decrypted_key:")
            print(f"     id: {result.id}")
            print(f"     key_type: {result.key_type}")
            print(f"     status: {result.status}")
            print(f"     name: {result.name}")
            
            # Verify key_type is correct
            if result.key_type == 'aead-det':
                print(f"\n   ✓ key_type is correct: 'aead-det'")
            else:
                print(f"\n   ✗ key_type is incorrect: expected 'aead-det', got '{result.key_type}'")
                return False
            
            # Verify status is active
            if result.status == 'valid':
                print(f"   ✓ key status is valid")
            else:
                print(f"   ✗ key status is not valid: '{result.status}'")
                return False
            
            print(f"\n" + "=" * 60)
            print(f"COMPONENT 1 VERIFICATION: PASSED")
            print(f"Key genuinely exists in pgsodium's store")
            print(f"=" * 60)
            return True
        else:
            print(f"   ✗ Key NOT found in pgsodium.decrypted_key")
            print(f"   This means create_key() did not actually create a key")
            return False
            
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db_client.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
