# Block I Integration Guide

## Consumers

- **Block J (Query Federator)** — `GET /signals/document/{id}` for popularity ranking; `GET /signals/user/{id}` for personalisation boosts.
- **Block H (Graph)** — may consume activity edges separately; Block I does not store graph edges.
- **Block L (Assistant)** — per-user affinity features.

## Auth

JWT from Block A with scopes:

- `activity.ingest` — POST /activity/ingest
- `signals.read` — GET /signals/*

`tenant_id` is always taken from the token. Body `tenant_id` is ignored (and rejected if mismatched).

## Event bus

Topic: `ingest.activity.v1` (Block B). Set `KAFKA_ENABLED=true` to consume.

## Privacy

`GET /signals/document` returns `privacy_protected: true` and null numerics when distinct actors < tenant `privacy_threshold` (default 5).

## Local run

```powershell
cd services/block-i-signals
$env:PYTHONPATH = (Get-Location).Path
$env:SIGNALS_BACKEND = "mock"
uvicorn app.main:app --port 8089 --reload
```