# Block H Integration Guide

## Overview

Block H exposes tenant-isolated knowledge-graph APIs for Block J (Query Federator):

| Method | Path | Scope |
|--------|------|-------|
| POST | `/graph/traverse` (also `/api/v1/graph/traverse`) | `graph.read` |
| GET | `/people/search` | `people.read` |
| GET | `/graph/related/{id}` | `graph.read` |
| POST | `/admin/persons/merge` | `graph.admin` |
| POST | `/admin/persons/split` | `graph.admin` |

## Backends

| Env | Value | Notes |
|-----|-------|-------|
| `GRAPH_BACKEND` | `mock` | Phase 1 provisional signoff |
| `GRAPH_BACKEND` | `neo4j` | Phase 2 integration |

Neo4j databases are named `graph_tenant_{sanitized_tenant_id}` when multi-DB is available; otherwise the default `neo4j` database is used with mandatory `tenant_id` filters.

## Event ingestion

`GraphWriter.process_event` consumes `ingest.canonical.v1` envelopes:

```json
{
  "tenant_id": "tenant_h_test",
  "event_type": "DocumentCreated",
  "payload": { "document_id": "...", "owner_principal_id": "...", "...": "..." }
}
```

Supported event types: `DocumentCreated/Updated`, `PrincipalCreated/Updated`, `GroupCreated/Updated`, `ACLChanged`, `ActivityViewed`, `ActivityCommented`.

## Fixtures

Set `FIXTURES_PATH` to override the local `fixtures/` directory when Block Z publishes shared fixtures.

Regenerate:

```powershell
python fixtures/generate_fixtures.py
```

## Run locally

```powershell
cd services/block-h-graph
$env:PYTHONPATH = (Get-Location).Path
$env:GRAPH_BACKEND = "mock"
uvicorn app.main:app --port 8088 --reload
```

Phase 2 Neo4j:

```powershell
docker compose -f docker-compose.test.yml up -d
$env:GRAPH_BACKEND = "neo4j"
$env:NEO4J_URI = "bolt://localhost:7688"
$env:NEO4J_PASSWORD = "blockh-dev-password"
python -m pytest tests/ -v --tb=short -s
```
