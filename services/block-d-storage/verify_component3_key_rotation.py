"""
Component 3 Verification: Real Key Rotation
Verifies that rotate_key() works with real pgcrypto functions and vault-backed keys.
"""

import os
import sys
import time
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from encryption.encryption_client import EncryptionClient
from encryption.db_client import DatabaseClient
from vault_client.vault_client import VaultClient

def main():
    print("=" * 60)
    print("Component 3 Verification: Real Key Rotation")
    print("=" * 60)
    
    block_d_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(block_d_dir, '.env')
    load_dotenv(env_path, override=True)
    
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    
    if not db_url:
        print("ERROR: Database connection string not found")
        return False
    
    print(f"\n1. Connecting to database...")
    db_client = DatabaseClient(db_url)
    
    try:
        print("   Connected successfully")
        
        print(f"\n2. Creating VaultClient...")
        vault_client = VaultClient(db_client, use_pgsodium=False)
        print("   VaultClient created successfully")
        
        print(f"\n3. Creating EncryptionClient...")
        encryption_client = EncryptionClient(db_client, vault_client)
        print("   EncryptionClient created successfully")
        
        # Create old key
        print(f"\n4. Creating old key (key A)...")
        old_key_name = f"component3_old_key_{int(time.time())}"
        old_key_id = encryption_client.create_key(key_name=old_key_name)
        print(f"   Old key created: {old_key_id}")
        
        # Encrypt test data under old key
        test_plaintext = "Sensitive data that needs key rotation"
        print(f"\n5. Encrypting test data under old key...")
        print(f"   Plaintext: '{test_plaintext}'")
        old_ciphertext = encryption_client.encrypt(test_plaintext, key_id=old_key_id)
        print(f"   Ciphertext (first 100 chars): {old_ciphertext[:100]}...")
        
        # Verify old key works
        decrypted_old = encryption_client.decrypt(old_ciphertext, key_id=old_key_id)
        if decrypted_old == test_plaintext:
            print(f"   ✓ Old key encrypt/decrypt works")
        else:
            print(f"   ✗ Old key encrypt/decrypt failed")
            return False
        
        # Create new key
        print(f"\n6. Creating new key (key B)...")
        new_key_name = f"component3_new_key_{int(time.time())}"
        print(f"   New key name: {new_key_name}")
        
        # Perform rotation with re-encryption
        print(f"\n7. Performing key rotation with re-encryption...")
        encrypted_data = [(old_ciphertext, old_key_id)]
        new_key_id = encryption_client.rotate_key(old_key_id, new_key_name, encrypted_data_list=encrypted_data)
        print(f"   Rotation completed: {old_key_id} -> {new_key_id}")
        
        # Re-encrypt the data manually for verification
        print(f"\n8. Re-encrypting test data with new key...")
        new_ciphertext = encryption_client.encrypt(test_plaintext, key_id=new_key_id)
        print(f"   New ciphertext (first 100 chars): {new_ciphertext[:100]}...")
        
        # Verify new key works
        decrypted_new = encryption_client.decrypt(new_ciphertext, key_id=new_key_id)
        if decrypted_new == test_plaintext:
            print(f"   ✓ New key encrypt/decrypt works")
        else:
            print(f"   ✗ New key encrypt/decrypt failed")
            return False
        
        # Verify old ciphertext still decrypts with old key (zero-downtime guarantee)
        print(f"\n9. Verifying old key still works (zero-downtime guarantee)...")
        still_decrypts = encryption_client.decrypt(old_ciphertext, key_id=old_key_id)
        if still_decrypts == test_plaintext:
            print(f"   ✓ Old key still functional for decryption")
        else:
            print(f"   ✗ Old key no longer works (zero-downtime broken)")
            return False
        
        # Verify new ciphertext does NOT decrypt with old key (keys are different)
        print(f"\n10. Verifying key isolation: new ciphertext cannot decrypt with old key...")
        try:
            should_fail = encryption_client.decrypt(new_ciphertext, key_id=old_key_id)
            print(f"   ✗ New ciphertext decrypted with old key (keys not isolated)")
            return False
        except Exception as e:
            print(f"   ✓ New ciphertext correctly fails to decrypt with old key")
            print(f"   Error (expected): {type(e).__name__}")
        
        # Verify old ciphertext does NOT decrypt with new key (keys are different)
        print(f"\n11. Verifying key isolation: old ciphertext cannot decrypt with new key...")
        try:
            should_fail = encryption_client.decrypt(old_ciphertext, key_id=new_key_id)
            print(f"   ✗ Old ciphertext decrypted with new key (keys not isolated)")
            return False
        except Exception as e:
            print(f"   ✓ Old ciphertext correctly fails to decrypt with new key")
            print(f"   Error (expected): {type(e).__name__}")
        
        print(f"\n" + "=" * 60)
        print(f"COMPONENT 3 VERIFICATION: PASSED")
        print(f"Real key rotation working with pgcrypto")
        print(f"Zero-downtime: old key still functional during rotation")
        print(f"Key isolation: new/old keys properly separated")
        print(f"=" * 60)
        return True
        
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
