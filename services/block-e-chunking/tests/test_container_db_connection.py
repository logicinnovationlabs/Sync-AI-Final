"""
Test container-to-container DATABASE_URL connection end-to-end.
This script should be run inside the celery-worker container.
"""

import psycopg2
import sys

DATABASE_URL = "postgresql://postgres:postgres@postgres:5432/block_e"

print(f"Testing connection to: {DATABASE_URL}")

try:
    conn = psycopg2.connect(DATABASE_URL)
    print("✓ Connection successful")
    
    cursor = conn.cursor()
    cursor.execute("SELECT version()")
    version = cursor.fetchone()
    print(f"✓ PostgreSQL version: {version[0]}")
    
    cursor.close()
    conn.close()
    print("✓ Connection closed cleanly")
    
    sys.exit(0)
except Exception as e:
    print(f"✗ Connection failed: {e}")
    sys.exit(1)
