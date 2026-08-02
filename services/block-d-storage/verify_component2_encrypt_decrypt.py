"""
Component 2 Verification: Real Encrypt/Decrypt
Verifies that encrypt() and decrypt() work with real pgcrypto functions.
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
    print("Component 2 Verification: Real Encrypt/Decrypt")
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
        vault_client = VaultClient(db_client, use_pgsodium=False)  # Use table backend to avoid pgsodium
        print("   VaultClient created successfully")
        
        print(f"\n3. Creating EncryptionClient...")
        encryption_client = EncryptionClient(db_client, vault_client)
        print("   EncryptionClient created successfully")
        
        # Create a key for testing
        print(f"\n4. Creating test key...")
        key_name = f"component2_test_key_{int(time.time())}"
        key_id = encryption_client.create_key(key_name=key_name)
        print(f"   Key created with key_id: {key_id}")
        
        # Test plaintext
        test_plaintext = "Hello, World! This is a test message for encryption."
        print(f"\n5. Encrypting test plaintext...")
        print(f"   Plaintext: '{test_plaintext}'")
        
        ciphertext = encryption_client.encrypt(test_plaintext, key_id=key_id)
        print(f"   Ciphertext (base64): {ciphertext[:100]}...")  # Show first 100 chars
        print(f"   Ciphertext length: {len(ciphertext)} characters")
        
        # Sanity check: ciphertext should not equal plaintext
        print(f"\n6. Sanity check: ciphertext != plaintext")
        if ciphertext != test_plaintext:
            print(f"   ✓ Ciphertext differs from plaintext (encryption occurred)")
        else:
            print(f"   ✗ Ciphertext equals plaintext (encryption failed)")
            return False
        
        # Sanity check: ciphertext should not be human-readable
        print(f"\n7. Sanity check: ciphertext is not human-readable")
        try:
            # Try to decode as base64 and check if it looks like PGP data
            import base64
            decoded = base64.b64decode(ciphertext)
            if b'PGP' in decoded or not decoded.decode('utf-8', errors='ignore').isprintable():
                print(f"   ✓ Ciphertext appears to be encrypted (not human-readable)")
            else:
                print(f"   ✗ Ciphertext appears to be human-readable (encryption may have failed)")
                return False
        except Exception:
            print(f"   ✓ Ciphertext is not human-readable (base64 decode failed as expected)")
        
        # Decrypt
        print(f"\n8. Decrypting ciphertext...")
        decrypted = encryption_client.decrypt(ciphertext, key_id=key_id)
        print(f"   Decrypted: '{decrypted}'")
        
        # Verify round-trip
        print(f"\n9. Verifying round-trip correctness...")
        if decrypted == test_plaintext:
            print(f"   ✓ Decrypted matches original plaintext byte-for-byte")
            print(f"   Original:  '{test_plaintext}'")
            print(f"   Decrypted: '{decrypted}'")
        else:
            print(f"   ✗ Decrypted does NOT match original plaintext")
            print(f"   Original:  '{test_plaintext}'")
            print(f"   Decrypted: '{decrypted}'")
            return False
        
        # Test with different plaintext
        print(f"\n10. Testing with different plaintext...")
        test_plaintext2 = "Another test: 12345!@#$%"
        print(f"   Plaintext: '{test_plaintext2}'")
        
        ciphertext2 = encryption_client.encrypt(test_plaintext2, key_id=key_id)
        decrypted2 = encryption_client.decrypt(ciphertext2, key_id=key_id)
        
        if decrypted2 == test_plaintext2:
            print(f"   ✓ Second test also passed")
        else:
            print(f"   ✗ Second test failed")
            return False
        
        print(f"\n" + "=" * 60)
        print(f"COMPONENT 2 VERIFICATION: PASSED")
        print(f"Real encrypt/decrypt working with pgcrypto")
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
