"""
Check pgcrypto extension availability in PostgreSQL.
"""

import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from encryption.db_client import DatabaseClient

def main():
    print("Checking pgcrypto extension availability...")
    
    block_d_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(block_d_dir, '.env')
    load_dotenv(env_path, override=True)
    
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    
    if not db_url:
        print("ERROR: Database connection string not found")
        return False
    
    db_client = DatabaseClient(db_url)
    
    try:
        print("\n1. Checking pgcrypto in pg_available_extensions:")
        result = db_client.fetch_one("""
            SELECT name, default_version, installed_version
            FROM pg_available_extensions
            WHERE name = 'pgcrypto';
        """)
        
        if result:
            print(f"   Extension: {result.name}")
            print(f"   Default version: {result.default_version}")
            print(f"   Installed version: {result.installed_version}")
            
            if result.installed_version:
                print("   ✓ pgcrypto is already installed")
                return True
            else:
                print("   pgcrypto is available but not installed")
                print("\n2. Attempting to CREATE EXTENSION pgcrypto...")
                try:
                    db_client.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
                    print("   ✓ pgcrypto extension enabled successfully")
                    
                    # Verify it worked
                    result = db_client.fetch_one("""
                        SELECT name, default_version, installed_version
                        FROM pg_available_extensions
                        WHERE name = 'pgcrypto';
                    """)
                    if result and result.installed_version:
                        print(f"   ✓ Verification successful - installed version: {result.installed_version}")
                        return True
                    else:
                        print("   ✗ Verification failed")
                        return False
                except Exception as e:
                    print(f"   ✗ Failed to enable pgcrypto extension: {type(e).__name__}: {e}")
                    return False
        else:
            print("   ✗ pgcrypto is NOT present in pg_available_extensions")
            print("   STOP: pgcrypto is not available on this platform")
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
