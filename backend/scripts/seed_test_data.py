"""
Comprehensive seed script for Blocks D-J integration testing.

Seeds realistic test data into all backend services:
- Block D: MinIO buckets, Vault secrets, Postgres databases
- Block E: Documents for chunking
- Block F: OpenSearch indices with documents
- Block G: Qdrant collections with vectors
- Block H: Neo4j graph with nodes and edges
- Block I: Postgres activity events and signals
- Block J: Combined data for federated search
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

# Add backend directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings

# Test tenant configuration
TEST_TENANT = "test-integration"


async def seed_block_d_storage():
    """Seed Block D: Storage Substrate (MinIO, Vault, Postgres)."""
    print("\n" + "=" * 80)
    print("SEEDING BLOCK D: Storage Substrate")
    print("=" * 80)
    
    from app.storage.object_store import get_object_store
    from app.storage.vault_client import vault_client
    from app.storage.control_plane_db import ControlPlaneSessionLocal
    from app.models.tenant import Tenant
    
    # 1. Create test tenant in control plane
    async with ControlPlaneSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Tenant).where(Tenant.subdomain == TEST_TENANT)
        )
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            tenant = Tenant(
                tenant_id=uuid4(),
                name="Integration Test Tenant",
                subdomain=TEST_TENANT,
                tenancy_mode="isolated_db",
                config={"environment": "test"},
                db_host=settings.db_host,
                db_name=f"snyq_{TEST_TENANT}",
                db_user="postgres",
                db_secret_key=f"kv/tenant-{TEST_TENANT}/db_password",
            )
            session.add(tenant)
            await session.commit()
            print(f"[OK] Created test tenant: {TEST_TENANT}")
        else:
            print(f"[INFO] Test tenant already exists: {TEST_TENANT}")
    
    # 2. Seed Vault secrets
    test_secrets = {
        "api_key_slack": "xoxb-test-slack-token",
        "api_key_github": "ghp_test_github_token",
        "db_password": "test_password_secure_123",
        "encryption_key": "test-encryption-key-32-bytes!!"
    }
    
    for key, value in test_secrets.items():
        secret_path = f"kv/tenant-{TEST_TENANT}/{key}"
        await vault_client.set_secret(secret_path, value)
    
    print(f"[OK] Seeded {len(test_secrets)} secrets in Vault")
    
    # 3. Seed MinIO buckets and test files
    object_store = get_object_store()
    test_files = [
        ("test-doc-1.txt", b"This is a test document for integration testing."),
        ("test-doc-2.txt", b"Another document with different content for search."),
        ("test-doc-3.pdf", b"%PDF-1.4 fake PDF content for testing"),
    ]
    
    for filename, content in test_files:
        object_key = f"{TEST_TENANT}/documents/{filename}"
        await object_store.put(object_key, content)
    
    print(f"[OK] Seeded {len(test_files)} test files in MinIO")
    print(f"[OK] Block D seeding complete")


async def seed_block_e_chunking():
    """Seed Block E: Chunking - documents for processing."""
    print("\n" + "=" * 80)
    print("SEEDING BLOCK E: Chunking")
    print("=" * 80)
    
    from app.storage.database_client import get_database_client
    
    db_client = get_database_client()
    
    # Create test documents in tenant database
    documents = [
        {
            "doc_id": "doc-e-001",
            "title": "Engineering Handbook",
            "content": "This is the engineering handbook. " * 50,
            "source": "confluence",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "doc_id": "doc-e-002",
            "title": "Product Roadmap Q3",
            "content": "Product roadmap for Q3 2026. " * 30,
            "source": "gdrive",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "doc_id": "doc-e-003",
            "title": "Meeting Notes - Architecture Review",
            "content": "Architecture review meeting notes. " * 40,
            "source": "slack",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    ]
    
    for doc in documents:
        await db_client.store_document(TEST_TENANT, doc["doc_id"], json.dumps(doc))
    
    print(f"[OK] Seeded {len(documents)} documents for chunking")
    print(f"[OK] Block E seeding complete")


async def seed_block_f_lexical():
    """Seed Block F: Lexical Search (OpenSearch)."""
    print("\n" + "=" * 80)
    print("SEEDING BLOCK F: Lexical Search")
    print("=" * 80)
    
    from app.services.lexical.opensearch_store import OpenSearchStore
    
    store = OpenSearchStore()
    await store.ensure_tenant(TEST_TENANT)
    
    # Index test documents
    documents = [
        {
            "doc_id": "doc-f-001",
            "title": "Python Best Practices",
            "content": "Learn Python best practices for writing clean, maintainable code.",
            "acl_principals": ["user-alice", "group-engineering"],
            "source": "wiki",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "doc_id": "doc-f-002",
            "title": "FastAPI Tutorial",
            "content": "Complete guide to building APIs with FastAPI framework.",
            "acl_principals": ["user-bob", "group-engineering"],
            "source": "docs",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "doc_id": "doc-f-003",
            "title": "Docker Deployment Guide",
            "content": "Step-by-step guide for deploying applications with Docker.",
            "acl_principals": ["user-charlie", "group-devops"],
            "source": "confluence",
            "created_at": datetime.now(timezone.utc),
        },
    ]
    
    for doc in documents:
        await store.index_document(TEST_TENANT, doc)
    
    print(f"[OK] Indexed {len(documents)} documents in OpenSearch")
    print(f"[OK] Block F seeding complete")


async def seed_block_g_vector():
    """Seed Block G: Vector Search (Qdrant)."""
    print("\n" + "=" * 80)
    print("SEEDING BLOCK G: Vector Search")
    print("=" * 80)
    
    from app.services.vector.qdrant_store import QdrantVectorStore
    import numpy as np
    
    store = QdrantVectorStore()
    await store.ensure_tenant(TEST_TENANT)
    
    # Create test vectors (using fake embeddings for testing)
    documents = [
        {
            "doc_id": "doc-g-001",
            "embedding": np.random.rand(settings.embedding_dimension).tolist(),
            "title": "Machine Learning Introduction",
            "content": "Introduction to machine learning concepts and algorithms.",
            "acl_principals": ["user-alice", "group-datascience"],
            "source": "gdrive",
            "model_version": "text-embedding-3-small",
        },
        {
            "doc_id": "doc-g-002",
            "embedding": np.random.rand(settings.embedding_dimension).tolist(),
            "title": "Deep Learning with PyTorch",
            "content": "Learn deep learning using PyTorch framework.",
            "acl_principals": ["user-bob", "group-datascience"],
            "source": "github",
            "model_version": "text-embedding-3-small",
        },
        {
            "doc_id": "doc-g-003",
            "embedding": np.random.rand(settings.embedding_dimension).tolist(),
            "title": "Natural Language Processing",
            "content": "NLP techniques and applications in modern AI.",
            "acl_principals": ["user-charlie", "group-research"],
            "source": "wiki",
            "model_version": "text-embedding-3-small",
        },
    ]
    
    for doc in documents:
        await store.index_vector(TEST_TENANT, doc)
    
    print(f"[OK] Indexed {len(documents)} vectors in Qdrant")
    print(f"[OK] Block G seeding complete")


async def seed_block_h_graph():
    """Seed Block H: Knowledge Graph (Neo4j)."""
    print("\n" + "=" * 80)
    print("SEEDING BLOCK H: Knowledge Graph")
    print("=" * 80)
    
    from app.services.graph.neo4j_store import Neo4jGraphStore
    
    store = Neo4jGraphStore()
    await store.ensure_tenant(TEST_TENANT)
    
    # Create person nodes
    persons = [
        {"node_id": "person-alice", "display_name": "Alice Smith", "email": "alice@example.com"},
        {"node_id": "person-bob", "display_name": "Bob Johnson", "email": "bob@example.com"},
        {"node_id": "person-charlie", "display_name": "Charlie Brown", "email": "charlie@example.com"},
    ]
    
    for person in persons:
        await store.upsert_node(TEST_TENANT, "Person", person["node_id"], person)
    
    # Create document nodes
    documents = [
        {"node_id": "doc-h-001", "title": "Q3 Strategy Doc"},
        {"node_id": "doc-h-002", "title": "Engineering Roadmap"},
        {"node_id": "doc-h-003", "title": "Product Specs"},
    ]
    
    for doc in documents:
        await store.upsert_node(TEST_TENANT, "Document", doc["node_id"], doc)
    
    # Create relationships
    edges = [
        ("person-alice", "doc-h-001", "AUTHORED"),
        ("person-bob", "doc-h-002", "AUTHORED"),
        ("person-charlie", "doc-h-003", "AUTHORED"),
        ("person-alice", "doc-h-002", "VIEWED"),
        ("person-bob", "doc-h-003", "VIEWED"),
        ("person-charlie", "doc-h-001", "COMMENTED_ON"),
    ]
    
    for source, target, rel_type in edges:
        await store.upsert_edge(TEST_TENANT, rel_type, source, target)
    
    print(f"[OK] Created {len(persons)} person nodes, {len(documents)} document nodes")
    print(f"[OK] Created {len(edges)} relationships")
    print(f"[OK] Block H seeding complete")


async def seed_block_i_signals():
    """Seed Block I: Activity Signals (Postgres)."""
    print("\n" + "=" * 80)
    print("SEEDING BLOCK I: Activity Signals")
    print("=" * 80)
    
    from app.services.signals.postgres_store import PostgresActivityStore
    from app.models.activity import ActivityEvent, ActivityConfig
    
    store = PostgresActivityStore()
    
    # Configure tenant
    config = ActivityConfig(
        tenant_id=TEST_TENANT,
        privacy_threshold=5,
        retention_days=90,
        high_privacy_retention_days=30,
    )
    await store.ensure_tenant(TEST_TENANT, config)
    
    # Create activity events
    now = datetime.now(timezone.utc)
    events = []
    
    # Multiple users viewing the same document (should show in signals)
    for i in range(10):
        events.append(ActivityEvent(
            event_id=f"event-view-{i}",
            actor_principal_id=f"user-{i}",
            object_id="doc-popular",
            event_type="view",
            source_system="web",
            event_time=now - timedelta(hours=i),
        ))
    
    # Single user editing a document
    events.append(ActivityEvent(
        event_id="event-edit-1",
        actor_principal_id="user-alice",
        object_id="doc-alice-draft",
        event_type="edit",
        source_system="web",
        event_time=now - timedelta(hours=1),
    ))
    
    # Comments on a document
    for i in range(3):
        events.append(ActivityEvent(
            event_id=f"event-comment-{i}",
            actor_principal_id=f"user-{i}",
            object_id="doc-discussion",
            event_type="comment",
            source_system="slack",
            event_time=now - timedelta(hours=i),
        ))
    
    for event in events:
        await store.ingest_event(TEST_TENANT, event)
    
    print(f"[OK] Ingested {len(events)} activity events")
    print(f"[OK] Block I seeding complete")


async def seed_all_blocks():
    """Run all seed functions in sequence."""
    print("\n" + "=" * 80)
    print("COMPREHENSIVE DATA SEEDING FOR BLOCKS D-J")
    print("=" * 80)
    print(f"Test Tenant: {TEST_TENANT}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    
    try:
        await seed_block_d_storage()
        await seed_block_e_chunking()
        await seed_block_f_lexical()
        await seed_block_g_vector()
        await seed_block_h_graph()
        await seed_block_i_signals()
        
        print("\n" + "=" * 80)
        print("[OK] ALL BLOCKS SEEDED SUCCESSFULLY")
        print("=" * 80)
        print("\nYou can now run integration tests with:")
        print(f"  cd backend")
        print(f"  pytest tests/test_block_*_signoff.py -v --real-backends")
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("[ERROR] SEEDING FAILED")
        print("=" * 80)
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(seed_all_blocks())
