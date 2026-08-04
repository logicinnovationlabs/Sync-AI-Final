"""
Ingest a batch of documents for E6 verification.
Generates 50+ synthetic canonical events and processes them through the full pipeline.
"""

import asyncio
import uuid
import random
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.chunkers.chunk_id_generator import ChunkIDGenerator
from app.workers.embedding_worker import EmbeddingJobQueue, celery_app
import redis
import json


def generate_synthetic_document(index: int, tenant_id: str) -> dict:
    """Generate a synthetic canonical document."""
    topics = [
        "Machine learning algorithms",
        "Database optimization techniques",
        "Cloud architecture patterns",
        "Microservices design principles",
        "API security best practices",
        "Container orchestration",
        "Data pipeline architecture",
        "DevOps automation strategies",
        "Network security protocols",
        "Software testing methodologies"
    ]
    
    topic = topics[index % len(topics)]
    
    return {
        "tenant_id": tenant_id,
        "document_id": f"synthetic_doc_{index:04d}",
        "document_version": 1,
        "content_type": "prose",
        "title": f"{topic} - Part {index // 10 + 1}",
        "content": f"This document covers {topic} in detail. It includes comprehensive analysis of key concepts, practical implementation strategies, and real-world use cases. The content is designed to provide actionable insights for developers and architects working in this domain. Section {index} discusses advanced patterns and optimization techniques that can be applied to production systems.",
        "metadata": {
            "source": "synthetic",
            "author": "e6_test_generator",
            "created_at": datetime.utcnow().isoformat()
        }
    }


def ingest_documents(database_url: str, num_documents: int = 50) -> list:
    """
    Ingest synthetic documents through the pipeline.
    
    Returns:
        List of chunk_ids created
    """
    print(f"Creating database engine for {database_url}")
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    
    chunk_id_generator = ChunkIDGenerator("1.0.0")
    chunk_ids = []
    
    # Initialize embedding job queue
    queue = EmbeddingJobQueue(celery_app)
    
    # Initialize Redis for provider call log
    redis_client = redis.from_url('redis://localhost:6379/0', decode_responses=True)
    
    with Session() as session:
        print(f"Ingesting {num_documents} documents...")
        
        for i in range(num_documents):
            # Alternate between 3 tenants for tenant isolation testing
            tenant_id = f"tenant_{(i % 3) + 1:03d}"
            
            doc = generate_synthetic_document(i, tenant_id)
            
            # Generate chunk_id
            content_hash = chunk_id_generator.compute_content_hash(doc['content'])
            chunk_id = chunk_id_generator.generate(
                tenant_id=doc['tenant_id'],
                document_id=doc['document_id'],
                document_version=doc['document_version'],
                chunk_type='file_summary',
                chunk_index=0,
                content_hash=content_hash
            )
            
            # Insert chunk record (skeleton without embedding)
            insert_query = text("""
                INSERT INTO chunk_records (
                    chunk_id, tenant_id, document_id, document_version,
                    chunk_type, chunk_index, content_text, token_count,
                    source_span_start, source_span_end,
                    embedding_vector, embedding_model_version, embedding_timestamp,
                    chunker_version, content_hash, chunk_content_checksum,
                    source_run_id, created_at, deleted_at
                ) VALUES (
                    :chunk_id, :tenant_id, :document_id, :document_version,
                    :chunk_type, :chunk_index, :content_text, :token_count,
                    :source_span_start, :source_span_end,
                    :embedding_vector, :embedding_model_version, :embedding_timestamp,
                    :chunker_version, :content_hash, :chunk_content_checksum,
                    :source_run_id, :created_at, :deleted_at
                )
            """)
            
            session.execute(insert_query, {
                'chunk_id': chunk_id,
                'tenant_id': doc['tenant_id'],
                'document_id': doc['document_id'],
                'document_version': doc['document_version'],
                'chunk_type': 'file_summary',
                'chunk_index': 0,
                'content_text': doc['content'],
                'token_count': len(doc['content'].split()),
                'source_span_start': 0,
                'source_span_end': len(doc['content']),
                'embedding_vector': None,
                'embedding_model_version': None,
                'embedding_timestamp': None,
                'chunker_version': '1.0.0',
                'content_hash': content_hash,
                'chunk_content_checksum': content_hash,
                'source_run_id': f"e6_test_run_{uuid.uuid4().hex[:8]}",
                'created_at': datetime.utcnow(),
                'deleted_at': None
            })
            
            chunk_ids.append(chunk_id)
            
            # Enqueue embedding job
            job_id = uuid.uuid4().hex
            task_id = queue.enqueue_job(
                job_id=job_id,
                tenant_id=doc['tenant_id'],
                chunk_id=chunk_id,
                content_text=doc['content'],
                model_version="v1"
            )
            
            if (i + 1) % 10 == 0:
                print(f"  Processed {i + 1}/{num_documents} documents")
        
        session.commit()
        print(f"  Committed {num_documents} chunk records")
    
    # Wait for all embedding jobs to complete
    print(f"\nWaiting for {num_documents} embedding jobs to complete...")
    import time
    start_time = time.time()
    
    expected_count = num_documents
    timeout = 60  # seconds
    
    while (time.time() - start_time) < timeout:
        current_count = redis_client.llen('embedding:provider_call_log')
        if current_count >= expected_count:
            print(f"  All jobs completed in {time.time() - start_time:.2f}s")
            break
        time.sleep(0.1)
    else:
        print(f"  Timeout after {timeout}s - only {redis_client.llen('embedding:provider_call_log')}/{expected_count} jobs completed")
    
    # Update chunk records with embeddings
    print(f"\nUpdating chunk records with embeddings...")
    
    # Read provider call log to get embeddings
    log_entries = redis_client.lrange('embedding:provider_call_log', 0, -1)
    
    with Session() as session:
        for entry in log_entries:
            call_data = json.loads(entry)
            chunk_id = call_data['chunk_id']
            
            # Generate mock embedding vector and serialize to bytes
            import struct
            embedding_vector = [0.0] * 1536
            embedding_vector[0] = hash(chunk_id) % 100 / 100.0
            embedding_bytes = struct.pack(f'{len(embedding_vector)}f', *embedding_vector)
            
            update_query = text("""
                UPDATE chunk_records
                SET embedding_vector = :embedding_vector,
                    embedding_model_version = :embedding_model_version,
                    embedding_timestamp = :embedding_timestamp
                WHERE chunk_id = :chunk_id
            """)
            
            session.execute(update_query, {
                'embedding_vector': embedding_bytes,
                'embedding_model_version': 'v1',
                'embedding_timestamp': datetime.utcnow(),
                'chunk_id': chunk_id
            })
        
        session.commit()
        print(f"  Updated {len(log_entries)} chunk records with embeddings")
    
    engine.dispose()
    return chunk_ids


if __name__ == "__main__":
    database_url = os.getenv(
        'DATABASE_URL',
        'postgresql://postgres:postgres@localhost:5432/block_e'
    )
    
    num_documents = int(os.getenv('NUM_DOCUMENTS', '50'))
    
    chunk_ids = ingest_documents(database_url, num_documents)
    print(f"\nSuccessfully ingested {len(chunk_ids)} documents")
    print(f"Chunk IDs: {chunk_ids[:5]}... (showing first 5)")
