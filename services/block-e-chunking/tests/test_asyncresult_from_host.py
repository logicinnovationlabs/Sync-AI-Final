"""
Test whether AsyncResult.ready() works from the host against the test script's backend URL.
This verifies the claimed root cause for the Celery timeout.
"""

import redis
from celery import Celery
import time

# Use the exact same backend URL as the test script
celery_app = Celery(
    'embedding_worker',
    broker='redis://localhost:6379/1',
    backend='redis://localhost:6379/2'
)

# Connect to Redis to check if results are being written
redis_client = redis.from_url('redis://localhost:6379/2', decode_responses=False)

print("=" * 80)
print("Testing AsyncResult.ready() from host against redis://localhost:6379/2")
print("=" * 80)

# Check if there are any existing results in the backend
print("\n[1] Checking for existing results in Redis DB 2...")
keys = redis_client.keys('*')
print(f"   Found {len(keys)} keys in Redis DB 2")

if keys:
    print(f"   Sample keys: {keys[:5]}")
    for key in keys[:3]:
        value = redis_client.get(key)
        print(f"   {key}: {value[:100] if value else 'None'}...")

# Try to get a task result using AsyncResult
print("\n[2] Testing AsyncResult with a known task ID...")
# Use a task ID that might exist from previous runs
test_task_id = "416298bb-0029-4fce-bc44-a2b91a25018d"  # From earlier E5 test

from celery.result import AsyncResult
result = AsyncResult(test_task_id, app=celery_app)

print(f"   Task ID: {test_task_id}")
print(f"   State: {result.state}")
print(f"   Ready: {result.ready()}")
print(f"   Result: {result.result if result.ready() else 'Not ready'}")

# Try submitting a new task and checking AsyncResult
print("\n[3] Submitting a new task and testing AsyncResult.ready()...")
result = celery_app.send_task(
    'app.workers.embedding_worker.embedding_task',
    args=[{
        'job_id': 'test_asyncresult_check',
        'tenant_id': 'tenant_test',
        'chunk_id': 'chunk_test',
        'content_text': 'Test content',
        'model_version_target': 'v1'
    }]
)

print(f"   Submitted task ID: {result.id}")

# Poll for completion using AsyncResult.ready()
start_time = time.time()
timeout = 10
while time.time() - start_time < timeout:
    if result.ready():
        print(f"   ✓ AsyncResult.ready() returned True after {time.time() - start_time:.2f}s")
        print(f"   State: {result.state}")
        print(f"   Result: {result.result}")
        break
    time.sleep(0.5)
else:
    print(f"   ✗ AsyncResult.ready() timed out after {timeout}s")
    print(f"   Final state: {result.state}")

print("\n" + "=" * 80)
print("Test complete")
print("=" * 80)
