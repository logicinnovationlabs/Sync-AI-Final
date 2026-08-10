"""
Sweep test data from dev database to remove stale pre-bump rows.
"""

from sqlalchemy import create_engine, text

engine = create_engine('postgresql://postgres:postgres@localhost:5432/block_e')

with engine.begin() as conn:
    # Count test chunk records
    result = conn.execute(text("SELECT COUNT(*) FROM chunk_records WHERE chunk_id LIKE 'test%'"))
    chunk_count = result.scalar()
    print(f"Test chunk records: {chunk_count}")
    
    # Count test embedding jobs
    result = conn.execute(text("SELECT COUNT(*) FROM embedding_jobs WHERE job_id LIKE 'test%'"))
    job_count = result.scalar()
    print(f"Test embedding jobs: {job_count}")
    
    # Delete test chunk records
    result = conn.execute(text("DELETE FROM chunk_records WHERE chunk_id LIKE 'test%'"))
    print(f"Deleted {result.rowcount} test chunk records")
    
    # Delete test embedding jobs
    result = conn.execute(text("DELETE FROM embedding_jobs WHERE job_id LIKE 'test%'"))
    print(f"Deleted {result.rowcount} test embedding jobs")
    
print("Sweep complete")
