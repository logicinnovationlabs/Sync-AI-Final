"""
Attempt to enable the vault extension.
"""

import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from encryption.db_client import DatabaseClient

def main():
    print("Attempting to enable vault extension...")
    
    block_d_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(block_d_dir, '.env')
    load_dotenv(env_path, override=True)
    
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    
    if not db_url:
        print("ERROR: Database connection string not found")
        return False
    
    db_client = DatabaseClient(db_url)
    
    try:
        print("\n1. Attempting to CREATE EXTENSION vault...")
        db_client.execute("CREATE EXTENSION IF NOT EXISTS vault")
        print("   ✓ Vault extension enabled successfully")
        
        # Verify it worked
        result = db_client.fetch_one("SELECT 1 FROM pg_extension WHERE extname = 'vault'")
        if result:
            print("   ✓ Verification successful")
            return True
        else:
            print("   ✗ Verification failed")
            return False
            
    except Exception as e:
        print(f"   ✗ Failed to enable vault extension: {type(e).__name__}: {e}")
        return False
    finally:
        db_client.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
