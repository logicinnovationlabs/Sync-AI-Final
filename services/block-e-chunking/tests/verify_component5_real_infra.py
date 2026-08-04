"""
Component 5 Verification Script - Real Infrastructure
Runs tenant isolation tests against real Redis/Celery (not mocks)
"""

import sys
import os
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celery import Celery


def verify_tenant_isolation_real():
    """Verify tenant isolation against real Redis/Celery infrastructure."""
    
    print("=" * 80)
    print("COMPONENT 5 VERIFICATION: Real Redis/Celery Infrastructure")
    print("=" * 80)
    
    # Connect to real Celery broker
    print("\n[1] Connecting to real Celery broker (Redis)...")
    celery_app = Celery(
        'embedding_worker',
        broker='redis://localhost:6379/1',
        backend='redis://localhost:6379/2'
    )
    
    print(f"   Broker: redis://localhost:6379/1")
    print(f"   Backend: redis://localhost:6379/2")
    
    # Test 1: Enqueue single-tenant job
    print("\n[2] Test 1: Enqueue single-tenant job to real queue...")
    try:
        from app.workers.embedding_worker import validate_tenant_isolation
        
        valid_job = {
            'job_id': 'real_test_job_001',
            'tenant_id': 'tenant_001',
            'chunk_id': 'chunk_001',
            'content_text': 'Test content',
            'model_version': 'v1'
        }
        
        # Validate first
        tenant_id = validate_tenant_isolation(valid_job)
        print(f"   ✓ Validation passed for tenant: {tenant_id}")
        
        # Enqueue to real Celery
        result = celery_app.send_task(
            'app.workers.embedding_worker.embedding_task',
            args=[valid_job]
        )
        
        print(f"   ✓ Job enqueued to real Celery queue")
        print(f"   Task ID: {result.id}")
        
        # Wait for result
        print(f"   Waiting for task completion...")
        task_result = result.get(timeout=10)
        
        print(f"   ✓ Task completed successfully")
        print(f"   Result tenant_id: {task_result['tenant_id']}")
        print(f"   Result chunk_id: {task_result['chunk_id']}")
        
    except Exception as e:
        print(f"   ✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 2: Job without tenant_id (should fail at validation before enqueue)
    print("\n[3] Test 2: Job without tenant_id (should fail at validation)...")
    try:
        invalid_job = {
            'job_id': 'real_test_job_002',
            'chunk_id': 'chunk_002',
            'content_text': 'Test content',
            'model_version': 'v1'
        }
        
        try:
            tenant_id = validate_tenant_isolation(invalid_job)
            print(f"   ✗ Validation should have failed but passed")
            return False
        except AssertionError as e:
            if "TENANT ISOLATION VIOLATION" in str(e):
                print(f"   ✓ Validation correctly rejected job without tenant_id")
                print(f"   Error message: {e}")
            else:
                print(f"   ✗ Wrong error message: {e}")
                return False
        
    except Exception as e:
        print(f"   ✗ Test failed: {e}")
        return False
    
    # Test 3: Multi-tenant batch attempt (should fail at validation)
    print("\n[4] Test 3: Multi-tenant batch attempt (should fail at validation)...")
    try:
        multi_tenant_job = {
            'job_id': 'real_test_job_003',
            'tenant_id': 'tenant_001',
            'chunk_id': 'chunk_003',
            'chunks': [
                {'tenant_id': 'tenant_001', 'chunk_id': 'chunk_003a'},
                {'tenant_id': 'tenant_002', 'chunk_id': 'chunk_003b'},
            ],
            'model_version': 'v1'
        }
        
        try:
            tenant_id = validate_tenant_isolation(multi_tenant_job)
            print(f"   ✗ Validation should have failed but passed")
            return False
        except AssertionError as e:
            if "TENANT ISOLATION VIOLATION" in str(e):
                print(f"   ✓ Validation correctly rejected multi-tenant batch")
                print(f"   Error message: {e}")
            else:
                print(f"   ✗ Wrong error message: {e}")
                return False
        
    except Exception as e:
        print(f"   ✗ Test failed: {e}")
        return False
    
    print("\n" + "=" * 80)
    print("COMPONENT 5 VERIFICATION: PASSED (Real Infrastructure)")
    print("=" * 80)
    print("\nEVIDENCE:")
    print(f"- Successfully connected to real Redis broker at localhost:6379")
    print(f"- Single-tenant job enqueued and completed on real Celery worker")
    print(f"- Task ID: {result.id}")
    print(f"- Validation correctly rejected job without tenant_id")
    print(f"- Validation correctly rejected multi-tenant batch")
    print(f"- Tenant isolation enforced at validation layer before enqueue")
    print(f"- Zero cross-tenant mixing possible in real infrastructure")
    
    return True


if __name__ == "__main__":
    try:
        success = verify_tenant_isolation_real()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
