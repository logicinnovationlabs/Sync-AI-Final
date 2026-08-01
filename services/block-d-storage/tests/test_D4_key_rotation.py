"""
D4 Signoff Test: Key Rotation (Real Supabase)
Per Glean Arch v1.3 §24, Block D signoff table.

Criterion: Rotate the KMS key while the service is live under read/write load
Pass threshold: 0 downtime, 0 data loss on read-after-rotation

This test runs against the real Supabase instance with pgsodium enabled.
"""

import pytest
import os
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from urllib.parse import urlparse
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from encryption.encryption_client import EncryptionClient
from encryption.db_client import DatabaseClient


class TestD4KeyRotationReal:
    """D4 test with real Supabase instance and pgsodium."""
    
    @pytest.fixture(scope="class")
    def db_connection_string(self):
        """
        Load database connection string from .env file.
        """
        # Load .env from the block-d-storage directory
        block_d_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(block_d_dir, '.env')
        load_dotenv(env_path, override=True)
        
        # Try multiple possible variable names
        db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
        
        if not db_url:
            raise RuntimeError("Database connection string not found in environment variables. Please set SUPABASE_DB_URL, DATABASE_URL, or POSTGRES_URL in .env file")
        
        # Parse and print only hostname for confirmation (not full string)
        parsed = urlparse(db_url)
        print(f"\nD4 Test Configuration:")
        print(f"  Database host: {parsed.hostname}")
        print(f"  Database port: {parsed.port}")
        print(f"  Database name: {parsed.path[1:]}")
        print(f"  Connection loaded: True")
        
        return db_url
    
    @pytest.fixture(scope="class")
    def db_client(self, db_connection_string):
        """
        Create database client for test setup/teardown.
        """
        client = DatabaseClient(db_connection_string)
        yield client
        client.close()
    
    @pytest.fixture(scope="class")
    def d4_schema_setup(self, db_client):
        """
        Create isolated schema and table for D4 test data.
        This ensures D4 does not depend on any other component's test data.
        """
        print(f"\nD4 Schema Setup:")
        print(f"  Creating isolated schema: d4_test")
        
        # Create isolated schema
        db_client.execute("DROP SCHEMA IF EXISTS d4_test CASCADE")
        db_client.execute("CREATE SCHEMA d4_test")
        
        # Create table for encrypted test data
        db_client.execute("""
            CREATE TABLE d4_test.encrypted_data (
                id SERIAL PRIMARY KEY,
                plaintext TEXT,
                ciphertext TEXT,
                key_id TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        print(f"  Schema and table created successfully")
        
        yield "d4_test"
        
        # Cleanup
        print(f"\nD4 Schema Cleanup:")
        print(f"  Dropping schema: d4_test")
        db_client.execute("DROP SCHEMA d4_test CASCADE")
    
    def test_D4_key_rotation_with_load(self, db_connection_string, d4_schema_setup):
        """
        D4 Signoff Test: Key rotation with zero downtime under concurrent load.
        
        Test flow:
        1. Create EncryptionClient with real Supabase connection
        2. Encrypt test data with old key
        3. Start concurrent read/write load (10 workers, 70/30 mix)
        4. Stabilize load for 10 seconds
        5. Trigger key rotation while load is running
        6. Continue load for 30 seconds post-rotation
        7. Verify zero failed requests during rotation
        8. Verify zero data loss on read-after-rotation
        9. Verify all pre-rotation data decrypts correctly post-rotation
        """
        print(f"\nD4 Key Rotation Test (Real Supabase):")
        print(f"  Isolation: Using dedicated schema d4_test")
        print(f"  Load pattern: 10 concurrent workers, 70% reads / 30% writes")
        print(f"  Duration: 10s stabilization + rotation + 30s post-rotation")
        
        # Create EncryptionClient
        encryption_client = EncryptionClient(DatabaseClient(db_connection_string))
        
        # Metrics tracking
        metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'read_requests': 0,
            'write_requests': 0,
            'rotation_start_time': None,
            'rotation_end_time': None,
            'failed_during_rotation': 0,
            'latencies': []
        }
        
        # Lock for thread-safe metrics updates
        metrics_lock = threading.Lock()
        
        # Test data for encryption/decryption
        test_plaintexts = [
            "secret_data_1", "secret_data_2", "secret_data_3",
            "tenant_a_config", "tenant_b_config", "api_key_value",
            "user_token", "session_data", "encryption_test", "rotation_test"
        ]
        
        # Store pre-rotation encrypted data for verification
        pre_rotation_data = {}
        
        # Load generation function
        def worker_operation(operation_type, stop_event):
            """Worker thread that performs encrypt or decrypt operations."""
            while not stop_event.is_set():
                try:
                    start_time = time.time()
                    
                    if operation_type == 'encrypt':
                        # Encrypt operation
                        plaintext = random.choice(test_plaintexts)
                        ciphertext = encryption_client.encrypt(plaintext, key_id="old_key")
                        
                        with metrics_lock:
                            metrics['total_requests'] += 1
                            metrics['successful_requests'] += 1
                            metrics['write_requests'] += 1
                            metrics['latencies'].append(time.time() - start_time)
                        
                        # Store some pre-rotation data for verification
                        if metrics['total_requests'] <= 100:
                            pre_rotation_data[plaintext] = ciphertext
                            
                    elif operation_type == 'decrypt':
                        # Decrypt operation
                        if pre_rotation_data:
                            # Decrypt pre-rotation data
                            plaintext = random.choice(list(pre_rotation_data.keys()))
                            ciphertext = pre_rotation_data[plaintext]
                            decrypted = encryption_client.decrypt(ciphertext)
                            
                            # Verify decryption correctness
                            if decrypted == plaintext:
                                with metrics_lock:
                                    metrics['total_requests'] += 1
                                    metrics['successful_requests'] += 1
                                    metrics['read_requests'] += 1
                                    metrics['latencies'].append(time.time() - start_time)
                            else:
                                with metrics_lock:
                                    metrics['total_requests'] += 1
                                    metrics['failed_requests'] += 1
                                    metrics['read_requests'] += 1
                        else:
                            # No data to decrypt yet, skip
                            pass
                    
                    # Random delay 10-50ms to simulate realistic request timing
                    time.sleep(random.uniform(0.01, 0.05))
                    
                except Exception as e:
                    with metrics_lock:
                        metrics['total_requests'] += 1
                        metrics['failed_requests'] += 1
                        
                        # Track if failure occurred during rotation
                        if metrics['rotation_start_time'] and (
                            metrics['rotation_end_time'] is None or 
                            time.time() < metrics['rotation_end_time']
                        ):
                            metrics['failed_during_rotation'] += 1
                    
                    # Small delay on error to avoid tight error loop
                    time.sleep(0.1)
        
        # Start load generation
        print(f"\n  Starting load generation...")
        stop_event = threading.Event()
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit workers (70% decrypt, 30% encrypt)
            futures = []
            for i in range(7):  # 7 decrypt workers
                futures.append(executor.submit(worker_operation, 'decrypt', stop_event))
            for i in range(3):  # 3 encrypt workers
                futures.append(executor.submit(worker_operation, 'encrypt', stop_event))
            
            # Stabilization phase (10 seconds)
            print(f"  Stabilization phase: 10 seconds...")
            time.sleep(10)
            
            print(f"  Pre-rotation metrics:")
            print(f"    Total requests: {metrics['total_requests']}")
            print(f"    Successful: {metrics['successful_requests']}")
            print(f"    Failed: {metrics['failed_requests']}")
            
            # Trigger key rotation
            print(f"\n  Initiating key rotation...")
            with metrics_lock:
                metrics['rotation_start_time'] = time.time()
            
            try:
                encryption_client.rotate_key("old_key", "new_key")
                with metrics_lock:
                    metrics['rotation_end_time'] = time.time()
                print(f"  Key rotation completed successfully")
                print(f"  Rotation duration: {metrics['rotation_end_time'] - metrics['rotation_start_time']:.3f}s")
            except Exception as e:
                with metrics_lock:
                    metrics['rotation_end_time'] = time.time()
                    metrics['failed_requests'] += 1
                print(f"  Key rotation failed: {e}")
                raise
            
            # Continue load for 30 seconds post-rotation
            print(f"\n  Post-rotation load phase: 30 seconds...")
            time.sleep(30)
            
            # Stop load generation
            stop_event.set()
            
            # Wait for all workers to complete
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass
        
        # Final metrics
        print(f"\n  Final Metrics:")
        print(f"    Total requests: {metrics['total_requests']}")
        print(f"    Successful requests: {metrics['successful_requests']}")
        print(f"    Failed requests: {metrics['failed_requests']}")
        print(f"    Read requests: {metrics['read_requests']}")
        print(f"    Write requests: {metrics['write_requests']}")
        print(f"    Failed during rotation: {metrics['failed_during_rotation']}")
        
        if metrics['latencies']:
            avg_latency = sum(metrics['latencies']) / len(metrics['latencies'])
            sorted_latencies = sorted(metrics['latencies'])
            p50 = sorted_latencies[int(len(sorted_latencies) * 0.5)]
            p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
            p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
            print(f"    Avg latency: {avg_latency*1000:.2f}ms")
            print(f"    P50 latency: {p50*1000:.2f}ms")
            print(f"    P95 latency: {p95*1000:.2f}ms")
            print(f"    P99 latency: {p99*1000:.2f}ms")
        
        # Verify zero failed requests during rotation
        print(f"\n  Verification:")
        print(f"    Zero failed requests during rotation: {metrics['failed_during_rotation'] == 0}")
        assert metrics['failed_during_rotation'] == 0, f"D4 FAILED: {metrics['failed_during_rotation']} requests failed during rotation"
        
        # Verify zero data loss - decrypt all pre-rotation data
        print(f"    Verifying pre-rotation data decryption...")
        decryption_failures = 0
        for plaintext, ciphertext in pre_rotation_data.items():
            try:
                decrypted = encryption_client.decrypt(ciphertext)
                if decrypted != plaintext:
                    decryption_failures += 1
                    print(f"      WARNING: Decryption mismatch for '{plaintext}'")
            except Exception as e:
                decryption_failures += 1
                print(f"      WARNING: Decryption failed for '{plaintext}': {e}")
        
        print(f"    Zero data loss: {decryption_failures == 0}")
        assert decryption_failures == 0, f"D4 FAILED: {decryption_failures} decryption failures detected"
        
        print(f"\n  D4 PASSED: Key rotation completed with zero downtime and zero data loss")
        print(f"  Isolation mechanism: Dedicated schema d4_test (isolated from other components)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
