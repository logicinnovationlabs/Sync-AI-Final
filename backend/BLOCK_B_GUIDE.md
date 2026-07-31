# Block B - Google Connector with Push-Based Ingestion

## Complete Implementation Guide & Testing Instructions

---

## Table of Contents

1. [What Is Block B?](#what-is-block-b)
2. [Architecture Overview](#architecture-overview)
3. [How It Works](#how-it-works)
4. [What Was Built](#what-was-built)
5. [Testing with Mock Data](#testing-with-mock-data)
6. [Testing with Your Real Gmail & Drive](#testing-with-real-data)
7. [Troubleshooting](#troubleshooting)

---

## What Is Block B?

Block B implements **Google Workspace connector with push-based ingestion** for Drive and Gmail. Instead of polling Google APIs repeatedly, we:

1. Do a **one-time backfill** when you first connect your account
2. Set up **push notifications** (webhooks) so Google tells us when something changes
3. Only **fetch the delta** (what changed) when notified
4. **Automatically renew** watch channels before they expire

This makes the system:
- **More efficient** - No wasteful polling
- **More responsive** - Changes appear almost instantly
- **More scalable** - Can handle thousands of accounts

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     YOUR GMAIL & DRIVE                       │
│  (Emails, Documents, Spreadsheets, Presentations, etc.)      │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ OAuth 2.0 (One-time consent)
                 ▼
┌─────────────────────────────────────────────────────────────┐
│              GOOGLE WORKSPACE APIs                           │
│  - Drive API (files, changes, watch)                         │
│  - Gmail API (messages, history, watch)                      │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ Push Notifications (Webhooks)
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                    SNYQ BACKEND (Block B)                    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  1. OAUTH MANAGER (Shared Token Management)         │   │
│  │     - Refreshes tokens automatically                 │   │
│  │     - One token for all Google services             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  2. CONNECTORS (Drive & Gmail Services)             │   │
│  │     - DriveConnector: Fetches files & changes        │   │
│  │     - GmailConnector: Fetches messages & history     │   │
│  │     - Transform to UnifiedDocument format            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  3. WEBHOOK RECEIVERS (FastAPI Routes)              │   │
│  │     - POST /webhooks/google/drive                    │   │
│  │     - POST /webhooks/google/gmail                    │   │
│  │     - Validate & enqueue Celery tasks                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  4. CELERY WORKERS (Async Task Processing)          │   │
│  │     - backfill_tenant_source (one-time full sync)    │   │
│  │     - process_drive_notification (delta sync)        │   │
│  │     - process_gmail_notification (delta sync)        │   │
│  │     - renew_watch_channels (periodic renewal)        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  5. INDEXER & STORAGE                                │   │
│  │     - Generate embeddings (Gemini or fake)           │   │
│  │     - Index to Qdrant vector database                │   │
│  │     - Store resume cursors in PostgreSQL             │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## How It Works

### The Lifecycle of a Document

#### **Phase 1: Initial Backfill (One-Time)**

```
User Connects Account
    ↓
OAuth Flow (Google consent screen)
    ↓
Store Access & Refresh Tokens
    ↓
Celery Task: backfill_tenant_source
    ↓
Fetch ALL files/emails (paginated)
    ↓
Transform to UnifiedDocument
    ↓
Generate Embeddings
    ↓
Index to Qdrant
    ↓
Store Final Cursor (Drive: pageToken, Gmail: historyId)
    ↓
Register Watch Channel
    ↓
DONE - Ready for incremental updates
```

#### **Phase 2: Incremental Updates (Ongoing)**

```
User Edits a Document in Drive OR Receives an Email
    ↓
Google sends Push Notification to your webhook
    ↓
Webhook validates (channel token check)
    ↓
Enqueue Celery Task (process_drive_notification)
    ↓
Task fetches ONLY changed items (using stored cursor)
    ↓
Transform & Index
    ↓
Update Cursor
    ↓
DONE - Document searchable in ~1-2 seconds
```

#### **Phase 3: Watch Renewal (Periodic)**

```
Celery Beat (runs every 24 hours)
    ↓
Check for watches expiring in next 48 hours
    ↓
Stop old channel
    ↓
Create new channel
    ↓
Store new expiration
    ↓
DONE - Continuous monitoring maintained
```

---

## What Was Built

### File Structure

```
backend/
├── app/
│   ├── connectors/
│   │   └── google/                        # ← GOOGLE CONNECTOR PACKAGE
│   │       ├── manifest.yaml              # Service definitions & metadata rules
│   │       ├── oauth.py                   # Shared OAuth token management
│   │       ├── watch_manager.py           # Watch channel creation & renewal
│   │       ├── webhooks.py                # FastAPI webhook routes
│   │       ├── clients/
│   │       │   ├── drive_client.py        # Drive API wrapper
│   │       │   └── gmail_client.py        # Gmail API wrapper
│   │       └── services/
│   │           ├── drive_service.py       # DriveConnector (implements BaseConnector)
│   │           └── gmail_service.py       # GmailConnector (implements BaseConnector)
│   │
│   ├── services/
│   │   ├── cursor_store.py                # Resume cursor storage (PostgreSQL)
│   │   ├── embedding.py                   # Gemini/fake embedding generation
│   │   ├── indexer.py                     # Metadata allowlisting + Qdrant indexing
│   │   └── registry.py                    # ← UPDATED: Manifest parsing & recursive discovery
│   │
│   ├── storage/
│   │   └── qdrant_client.py               # Vector database wrapper
│   │
│   └── workers/
│       ├── celery_app.py                  # Celery application config
│       ├── tasks.py                       # All 4 Celery tasks
│       └── beat_schedule.py               # Periodic task scheduling
│
├── tests/
│   ├── fixtures/google/                   # Mock API responses
│   │   ├── drive/                         # Drive fixtures
│   │   └── gmail/                         # Gmail fixtures
│   └── test_signoff_block_b.py            # B1-B7 signoff tests
│
├── docker-compose.yml                     # ← UPDATED: Added Qdrant, Celery worker, Celery beat
├── requirements.txt                       # ← UPDATED: Block B dependencies
└── .env.example                           # ← UPDATED: Block B environment variables
```

### Key Components Explained

#### 1. **OAuth Manager (`oauth.py`)**
- **What:** Manages Google OAuth tokens for ALL services (Drive, Gmail, Calendar, etc.)
- **Why:** One consent screen, one token, shared across all Google services
- **How:** Automatically refreshes expired tokens, stores securely

#### 2. **Drive & Gmail Clients (`clients/`)**
- **What:** Thin wrappers around google-api-python-client
- **Why:** Abstracts API complexity, makes testing easier
- **How:** Async methods for files.list, changes.list, messages.list, history.list, watch

#### 3. **Drive & Gmail Connectors (`services/`)**
- **What:** Implement `BaseConnector` interface
- **Why:** "Blind Orchestrator" pattern - sync.py never imports specific connectors
- **How:** 
  - `fetch_delta`: Backfill path (full traversal)
  - `fetch_since_page_token` / `fetch_since_history_id`: Incremental path
  - `transform`: Normalize to UnifiedDocument

#### 4. **Watch Manager (`watch_manager.py`)**
- **What:** Creates and renews watch channels/subscriptions
- **Why:** Google watch channels expire after ~7 days
- **How:**
  - Drive: `files.watch` creates a webhook channel
  - Gmail: `users.watch` creates a Pub/Sub subscription
  - Renewal happens 48 hours before expiry

#### 5. **Webhook Receivers (`webhooks.py`)**
- **What:** FastAPI routes that receive push notifications
- **Why:** Google sends notifications here when content changes
- **How:**
  - Validate channel token (Drive) or Pub/Sub auth (Gmail)
  - Enqueue Celery task for processing
  - Return immediately (< 1 second response time)

#### 6. **Celery Tasks (`workers/tasks.py`)**
- **What:** Async background jobs
- **Why:** Heavy operations (API calls, indexing) shouldn't block web server
- **How:**
  - `backfill_tenant_source`: One-time full sync, then register watch
  - `process_drive_notification`: Fetch Drive changes since last cursor
  - `process_gmail_notification`: Fetch Gmail history since last cursor
  - `renew_watch_channels`: Periodic Beat task

#### 7. **Cursor Store (`cursor_store.py`)**
- **What:** Stores resume cursors per tenant/source
- **Why:** Remember where we left off (Drive pageToken, Gmail historyId)
- **How:** PostgreSQL table with (tenant_id, source_type, cursor, watch_data)

#### 8. **Indexer (`indexer.py`)**
- **What:** Metadata allowlisting + embedding generation + Qdrant indexing
- **Why:** Only index allowed metadata (security), enable vector search
- **How:**
  - Filter metadata by manifest.yaml rules
  - Generate embeddings (Gemini or fake)
  - Upsert to Qdrant with tenant_id for isolation

---

## Testing with Mock Data

### Run Block B Signoff Tests

These tests validate all 7 criteria (B1-B7) using mocked Google APIs:

```powershell
cd C:\Users\prath\OneDrive\Desktop\SnyQ_Phase_2\backend

# Option 1: Run all signoff tests
pytest tests/test_signoff_block_b.py -v

# Option 2: Run specific test
pytest tests/test_signoff_block_b.py::test_B1_backfill_completeness -v

# Option 3: Run with detailed output
pytest tests/test_signoff_block_b.py -v -s --log-cli-level=DEBUG
```

**Expected Output:**
```
test_B1_backfill_completeness[google_drive-4] PASSED
test_B1_backfill_completeness[google_gmail-3] PASSED
test_B2_webhook_incremental_correctness[google_drive] PASSED
test_B2_webhook_incremental_correctness[google_gmail] PASSED
test_B3_webhook_authenticity_rejection PASSED
test_B4_rate_limit_resilience PASSED
test_B5_credential_leakage PASSED
test_B6_metadata_allowlist_enforcement[google_drive] PASSED
test_B6_metadata_allowlist_enforcement[google_gmail] PASSED
test_B7_watch_channel_renewal PASSED

========== 10 passed in 5.23s ==========
```

### What Each Test Validates

| Test | What It Checks | Pass Criteria |
|------|----------------|---------------|
| **B1** | Backfill completeness | All fixture documents indexed, 0 loss |
| **B2** | Webhook incremental | Fetches only delta, not full re-scan |
| **B3** | Webhook security | Forged notifications rejected |
| **B4** | Rate limit handling | Retries on 429, eventually succeeds |
| **B5** | Credential safety | No tokens in logs |
| **B6** | Metadata allowlist | Only allowed keys indexed |
| **B7** | Watch renewal | Expiring watches renewed automatically |

---

## Testing with Your Real Gmail & Drive

### Prerequisites

1. **Google Cloud Project**: You need a Google Cloud project with:
   - Drive API enabled
   - Gmail API enabled
   - OAuth 2.0 credentials (Client ID + Secret)
   - Pub/Sub topic (for Gmail push notifications)

2. **ngrok or Public URL**: Webhooks need a public URL to receive notifications

### Step-by-Step Setup

#### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project: "SnyQ Development"
3. Enable APIs:
   ```
   APIs & Services → Library
   → Search "Google Drive API" → Enable
   → Search "Gmail API" → Enable
   → Search "Cloud Pub/Sub API" → Enable
   ```

#### Step 2: Create OAuth Credentials

1. Go to: `APIs & Services → Credentials`
2. Click: `CREATE CREDENTIALS → OAuth client ID`
3. Application type: `Web application`
4. Name: `SnyQ Backend`
5. Authorized redirect URIs:
   ```
   http://localhost:8000/api/v1/connectors/google/callback
   https://your-ngrok-url.ngrok.io/api/v1/connectors/google/callback
   ```
6. Click `CREATE`
7. **Copy Client ID and Client Secret**

#### Step 3: Create Pub/Sub Topic (for Gmail)

```bash
# Install gcloud CLI if not already installed
# Then authenticate and set project
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Create topic
gcloud pubsub topics create gmail-watch-notifications

# Grant Gmail permission to publish to this topic
gcloud pubsub topics add-iam-policy-binding gmail-watch-notifications \
  --member=serviceAccount:gmail-api-push@system.gserviceaccount.com \
  --role=roles/pubsub.publisher

# Create subscription (for receiving messages)
gcloud pubsub subscriptions create gmail-watch-sub \
  --topic=gmail-watch-notifications \
  --push-endpoint=https://your-ngrok-url.ngrok.io/api/v1/webhooks/google/gmail
```

#### Step 4: Configure Environment Variables

Edit `.env`:

```bash
# Block B: Google OAuth
GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret-here
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/connectors/google/callback

# Block B: Pub/Sub (for Gmail)
GOOGLE_PUBSUB_PROJECT_ID=your-project-id
GOOGLE_PUBSUB_TOPIC=gmail-watch-notifications
GOOGLE_PUBSUB_VERIFICATION_TOKEN=your-secret-token-123

# Block B: Webhook base URL (use ngrok URL for testing)
WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok.io/api/v1

# Block B: Embedding (use 'fake' for testing, 'gemini' for production)
EMBEDDING_PROVIDER=fake
GEMINI_API_KEY=your-gemini-api-key-here
```

#### Step 5: Start Services

```powershell
cd C:\Users\prath\OneDrive\Desktop\SnyQ_Phase_2\backend

# Start all services (Postgres, Redis, Qdrant, App, Celery)
docker-compose up -d

# Check logs
docker-compose logs -f app
docker-compose logs -f celery_worker
```

#### Step 6: Expose Webhook with ngrok

```powershell
# In a separate terminal
ngrok http 8000

# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
# Update WEBHOOK_BASE_URL in .env
# Update Pub/Sub subscription endpoint
```

#### Step 7: Authorize Your Google Account

```python
# Create a script: scripts/authorize_google.py
import asyncio
from app.connectors.google.oauth import GoogleOAuthManager
from app.storage.redis_client import TenantPartitionedRedisClient

async def main():
    # Your credentials
    client_id = "YOUR_CLIENT_ID"
    client_secret = "YOUR_CLIENT_SECRET"
    scopes = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/gmail.readonly",
    ]
    
    # Initialize OAuth manager
    redis_client = TenantPartitionedRedisClient("redis://localhost:6379", "tenant123")
    oauth_manager = GoogleOAuthManager(redis_client, client_id, client_secret, scopes)
    
    # Generate authorization URL
    redirect_uri = "http://localhost:8000/api/v1/connectors/google/callback"
    auth_url = oauth_manager.build_authorization_url("tenant123", redirect_uri)
    
    print("\n" + "="*70)
    print("GOOGLE AUTHORIZATION")
    print("="*70)
    print("\n1. Open this URL in your browser:")
    print(f"\n{auth_url}\n")
    print("2. Sign in with your Google account")
    print("3. Grant permissions")
    print("4. Copy the 'code' parameter from the redirect URL")
    print("="*70 + "\n")
    
    code = input("Enter the authorization code: ")
    
    # Exchange code for tokens
    tokens = await oauth_manager.exchange_code_for_tokens("tenant123", code, redirect_uri)
    
    print("\n✓ Authorization successful!")
    print(f"Access token: {tokens['access_token'][:20]}...")
    print(f"Refresh token: {tokens.get('refresh_token', 'N/A')[:20]}...")
    print("\nTokens stored. You can now run backfill.\n")

if __name__ == "__main__":
    asyncio.run(main())
```

Run it:
```powershell
python scripts/authorize_google.py
```

#### Step 8: Run Backfill

```python
# Create script: scripts/run_backfill.py
from app.workers.tasks import backfill_tenant_source

# For Drive
result = backfill_tenant_source("tenant123", "google_drive")
print(f"Drive backfill: {result}")

# For Gmail
result = backfill_tenant_source("tenant123", "google_gmail")
print(f"Gmail backfill: {result}")
```

Or via Python shell:
```powershell
docker-compose exec app python

>>> from app.workers.tasks import backfill_tenant_source
>>> backfill_tenant_source.delay("tenant123", "google_drive")
<AsyncResult: abc-123-def-456>
```

#### Step 9: Test Incremental Updates

**For Drive:**
1. Go to your Google Drive
2. Create a new document or edit an existing one
3. Within 1-2 seconds, you should see:
   ```
   # In celery_worker logs:
   [2026-07-31 10:15:32] Processing Drive notification for tenant tenant123
   [2026-07-31 10:15:33] Drive notification processed: 1 indexed, 0 deleted
   ```

**For Gmail:**
1. Send yourself an email
2. Within 1-2 seconds, you should see:
   ```
   # In celery_worker logs:
   [2026-07-31 10:16:45] Processing Gmail notification for tenant tenant123
   [2026-07-31 10:16:46] Gmail notification processed: 1 indexed, 0 deleted
   ```

#### Step 10: Query Qdrant

```python
# scripts/query_documents.py
from app.storage.qdrant_client import qdrant_client
from app.services.embedding import embedding_service

async def search_documents(query_text):
    # Generate query embedding
    query_vector = await embedding_service.embed_text(query_text)
    
    # Search Qdrant
    results = await qdrant_client.search(
        query_vector=query_vector,
        limit=10,
        filters={"tenant_id": "tenant123"}
    )
    
    for doc in results:
        print(f"\nTitle: {doc['title']}")
        print(f"Source: {doc['source_type']}")
        print(f"Score: {doc['_score']:.4f}")
        print(f"URL: {doc['url']}")

# Run it
import asyncio
asyncio.run(search_documents("project proposal"))
```

---

## Troubleshooting

### Issue: "No module named 'google'"

**Solution:**
```powershell
pip install google-api-python-client google-auth-oauthlib google-generativeai
```

### Issue: "Token expired" or "Invalid credentials"

**Solution:**
1. Re-run authorization script
2. Check that refresh token is stored
3. Verify OAuth credentials in Google Cloud Console

### Issue: "Webhook not receiving notifications"

**Solution:**
1. Check ngrok is running: `ngrok http 8000`
2. Verify webhook URL in watch registration
3. Check firewall rules
4. Test webhook manually:
   ```powershell
   curl -X POST http://localhost:8000/api/v1/webhooks/google/drive \
     -H "X-Goog-Channel-Id: test" \
     -H "X-Goog-Channel-Token: test" \
     -H "X-Goog-Resource-Id: test" \
     -H "X-Goog-Resource-State: update"
   ```

### Issue: "Celery task stuck"

**Solution:**
```powershell
# Check Celery worker logs
docker-compose logs -f celery_worker

# Restart worker
docker-compose restart celery_worker

# Check task status in Redis
docker-compose exec redis redis-cli
> KEYS celery*
```

### Issue: "Rate limit exceeded (429)"

**Solution:**
- Tasks automatically retry with exponential backoff
- Check Google Cloud Console quotas
- Request quota increase if needed

---

## Next Steps

1. ✅ **Run signoff tests**: `pytest tests/test_signoff_block_b.py -v`
2. ✅ **Set up Google Cloud project** (follow Step 1-3 above)
3. ✅ **Configure environment** (Step 4)
4. ✅ **Authorize your account** (Step 7)
5. ✅ **Run backfill** (Step 8)
6. ✅ **Test live updates** (Step 9)
7. ✅ **Query documents** (Step 10)

---

## Support

If you encounter issues:
1. Check Docker logs: `docker-compose logs -f`
2. Check Celery worker logs: `docker-compose logs -f celery_worker`
3. Check Celery beat logs: `docker-compose logs -f celery_beat`
4. Verify Qdrant: http://localhost:6333/dashboard
5. Review this guide's troubleshooting section

---

**Block B is complete and production-ready!** 🎉
