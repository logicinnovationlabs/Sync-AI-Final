"""
D4 Signoff Test: Key Rotation (Local Postgres)
Per Glean Arch v1.3 §24, Block D signoff table.

Criterion: Rotate the KMS key while the service is live under read/write load
Pass threshold: 0 downtime, 0 data loss on read-after-rotation

This test runs against the local Postgres container with pgcrypto enabled.
"""

import pytest
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from encryption.encryption_client import EncryptionClient
from encryption.db_client import DatabaseClient
from vault_client.vault_client import VaultClient


class TestD4KeyRotationLocal:
    """D4 test with local Postgres instance and pgcrypto."""
    
    @pytest.fixture(scope="class")
    def db_connection_string(self):
        """
        Local Postgres connection string.
        """
        db_url = "postgresql://postgres:verify@localhost:5435/block_d_verify"
        
        print(f"\nD4 Test Configuration:")
        print(f"  Database host: localhost")
        print(f"  Database port: 5435")
        print(f"  Database name: block_d_verify")
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

        db_client.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        
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
        1. Create EncryptionClient with local Postgres connection
        2. Encrypt test data with old key
        3. Start concurrent read/write load (10 workers, 70/30 mix)
        4. Stabilize load for 5 seconds
        5. Trigger key rotation while load is running
        6. Continue load for 10 seconds post-rotation
        7. Verify zero failed requests during rotation
        8. Verify zero data loss on read-after-rotation
        9. Verify all pre-rotation data decrypts correctly post-rotation
        """
        print(f"\nD4 Key Rotation Test (Local Postgres):")
        print(f"  Isolation: Using dedicated schema d4_test")
        print(f"  Load pattern: 10 concurrent workers, 70% reads / 30% writes")
        print(f"  Duration: 5s stabilization + rotation + 10s post-rotation")
        
        # Create VaultClient and EncryptionClient
        db_client = DatabaseClient(db_connection_string)
        vault_client = VaultClient(db_client, use_pgsodium=False)  # Use table backend
        encryption_client = EncryptionClient(db_client, vault_client)
        
        # Use unique key names with timestamp to avoid conflicts
        timestamp = int(time.time())
        old_key_name = f"d4_test_old_key_{timestamp}"
        new_key_name = f"d4_test_new_key_{timestamp}"
        
        # Create real pgcrypto keys for the test
        print(f"\n  Creating pgcrypto keys...")
        old_key_id = encryption_client.create_key(old_key_name)
        print(f"  Old key created: key_id={old_key_id}, name={old_key_name}")
        
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
            'latencies': [],
            'active_key_id': old_key_id  # Track the currently active key
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
        # Format: {plaintext: (ciphertext, key_id)}
        pre_rotation_data = {}
        
        # Load generation function
        def worker_operation(operation_type, stop_event):
            """Worker thread that performs encrypt or decrypt operations."""
            while not stop_event.is_set():
                try:
                    start_time = time.time()
                    
                    if operation_type == 'encrypt':
                        # Encrypt operation - use currently active key
                        with metrics_lock:
                            current_key_id = metrics['active_key_id']
                        
                        plaintext = random.choice(test_plaintexts)
                        ciphertext = encryption_client.encrypt(plaintext, key_id=current_key_id)
                        
                        with metrics_lock:
                            metrics['total_requests'] += 1
                            metrics['successful_requests'] += 1
                            metrics['write_requests'] += 1
                            metrics['latencies'].append(time.time() - start_time)
                        
                        # Store some pre-rotation data for verification
                        # Store both ciphertext and the key_id used to encrypt it
                        if metrics['total_requests'] <= 50:
                            pre_rotation_data[plaintext] = (ciphertext, current_key_id)
                            
                    elif operation_type == 'decrypt':
                        # Decrypt operation
                        if pre_rotation_data:
                            # Decrypt pre-rotation data
                            plaintext = random.choice(list(pre_rotation_data.keys()))
                            ciphertext, key_id = pre_rotation_data[plaintext]
                            decrypted = encryption_client.decrypt(ciphertext, key_id=key_id)
                            
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
                    else:
                        time.sleep(0.01)  # Small delay if no operation
                        
                except Exception as e:
                    with metrics_lock:
                        metrics['total_requests'] += 1
                        metrics['failed_requests'] += 1
                        
                        # Track if failure occurred during rotation
                        if metrics['rotation_start_time'] and not metrics['rotation_end_time']:
                            metrics['failed_during_rotation'] += 1
        
        # Start load generation
        print(f"\n  Starting concurrent load generation...")
        stop_event = threading.Event()
        
        # Create thread pool with 10 workers (70% reads, 30% writes)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            # 7 readers (70%)
            for _ in range(7):
                futures.append(executor.submit(worker_operation, 'decrypt', stop_event))
            
            # 3 writers (30%)
            for _ in range(3):
                futures.append(executor.submit(worker_operation, 'encrypt', stop_event))
            
            # Stabilize load for 5 seconds
            print(f"  Stabilizing load for 5 seconds...")
            time.sleep(5)
            
            # Trigger key rotation
            print(f"\n  Triggering key rotation...")
            metrics['rotation_start_time'] = time.time()
            
            # Create new key
            new_key_id = encryption_client.create_key(new_key_name)
            print(f"  New key created: key_id={new_key_id}, name={new_key_name}")
            
            # Switch active key
            with metrics_lock:
                metrics['active_key_id'] = new_key_id
            
            rotation_duration = time.time() - metrics['rotation_start_time']
            metrics['rotation_end_time'] = time.time()
            print(f"  Key rotation completed in {rotation_duration:.3f}s")
            
            # Continue load for 10 seconds post-rotation
            print(f"  Continuing load for 10 seconds post-rotation...")
            time.sleep(10)
            
            # Stop load generation
            stop_event.set()
            
            # Wait for all workers to finish
            for future in futures:
                future.cancel()
        
        # Calculate final metrics
        avg_latency = sum(metrics['latencies']) / len(metrics['latencies']) if metrics['latencies'] else 0
        
        print(f"\nD4 Key Rotation Test Results:")
        print(f"  Total requests: {metrics['total_requests']}")
        print(f"  Successful requests: {metrics['successful_requests']}")
        print(f"  Failed requests: {metrics['failed_requests']}")
        print(f"  Read requests: {metrics['read_requests']}")
        print(f"  Write requests: {metrics['write_requests']}")
        print(f"  Failed during rotation: {metrics['failed_during_rotation']}")
        print(f"  Rotation duration: {rotation_duration:.3f}s")
        print(f"  Average latency: {avg_latency:.2f}ms")
        
        # Verify zero downtime
        assert metrics['failed_during_rotation'] == 0, f"D4 FAILED: {metrics['failed_during_rotation']} requests failed during rotation"
        assert metrics['failed_requests'] == 0, f"D4 FAILED: {metrics['failed_requests']} total requests failed"
        
        # Verify pre-rotation data still decrypts correctly
        print(f"\n  Verifying pre-rotation data decrypts correctly...")
        pre_rotation_decrypt_success = 0
        pre_rotation_decrypt_total = 0
        
        for plaintext, (ciphertext, key_id) in pre_rotation_data.items():
            pre_rotation_decrypt_total += 1
            try:
                decrypted = encryption_client.decrypt(ciphertext, key_id=key_id)
                if decrypted == plaintext:
                    pre_rotation_decrypt_success += 1
            except Exception as e:
                print(f"  WARNING: Failed to decrypt pre-rotation data: {e}")
        
        print(f"  Pre-rotation decryption: {pre_rotation_decrypt_success}/{pre_rotation_decrypt_total} successful")
        
        assert pre_rotation_decrypt_success == pre_rotation_decrypt_total, \
            f"D4 FAILED: Only {pre_rotation_decrypt_success}/{pre_rotation_decrypt_total} pre-rotation items decrypted correctly"
        
        print(f"  D4 PASSED: Zero downtime, zero data loss, all pre-rotation data decrypts correctly")
        
        # Cleanup vault keys
        try:
            vault_client.delete(old_key_name)
            vault_client.delete(new_key_name)
        except Exception:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])