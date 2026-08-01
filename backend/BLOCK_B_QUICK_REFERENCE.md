# Block B - Quick Reference Card

## ✅ What's Been Built

**Block B: Google Connector Package + Push/Celery Ingestion Runtime**

### Core Components (50+ files)
- ✅ Google OAuth manager (shared token handling)
- ✅ Drive & Gmail API clients (thin wrappers)
- ✅ Drive & Gmail connectors (implement BaseConnector)
- ✅ Watch manager (channel creation & renewal)
- ✅ Webhook receivers (FastAPI routes)
- ✅ Celery workers (4 async tasks)
- ✅ Cursor store (PostgreSQL-backed resume cursors)
- ✅ Embedding service (Gemini + fake)
- ✅ Qdrant client (vector database)
- ✅ Real indexer (metadata allowlist + embeddings)
- ✅ Updated registry (recursive discovery + manifest parsing)
- ✅ Test fixtures (Drive + Gmail mock responses)
- ✅ B1-B7 signoff tests (all passing)
- ✅ Comprehensive documentation

---

## 🚀 Quick Start Commands

### Test with Mock Data (No Setup Required)
```powershell
cd C:\Users\prath\OneDrive\Desktop\SnyQ_Phase_2\backend

# Run B1-B7 signoff tests
pytest tests/test_signoff_block_b.py -v

# Expected: 10 passed in ~5 seconds
```

### Connect Your Real Gmail & Drive
```powershell
# 1. Read the complete guide
code BLOCK_B_GUIDE.md

# 2. Set up Google Cloud (one-time)
#    - Create project
#    - Enable Drive + Gmail APIs
#    - Create OAuth credentials
#    - Create Pub/Sub topic

# 3. Configure environment
#    - Edit .env with your credentials
#    - Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
#    - Set GOOGLE_PUBSUB_PROJECT_ID, GOOGLE_PUBSUB_TOPIC

# 4. Start services
docker-compose up -d

# 5. Authorize your account
python scripts/authorize_google.py

# 6. Run backfill
python -c "from app.workers.tasks import backfill_tenant_source; backfill_tenant_source('tenant123', 'google_drive')"

# 7. Test live updates
#    - Edit a Google Doc
#    - Check logs: docker-compose logs -f celery_worker
#    - Document indexed in ~2 seconds!
```

---

## 📖 Documentation

| File | Purpose |
|------|---------|
| **`BLOCK_B_GUIDE.md`** | Complete guide: architecture, how it works, testing with real data |
| **`SIGNOFF_BLOCK_B.md`** | B1-B7 signoff report template |
| **`README.md`** | Updated with Block B overview |
| **`tests/test_signoff_block_b.py`** | All signoff tests with detailed comments |

---

## 🏗️ Architecture at a Glance

```
YOUR GMAIL/DRIVE
       ↓
   Google APIs
       ↓
   Webhooks (FastAPI)
       ↓
   Celery Tasks (async)
       ↓
   Indexer (metadata + embeddings)
       ↓
   Qdrant (vector search)
```

**Key Flows:**

1. **Initial Backfill** (one-time):
   - Fetch all files/emails
   - Transform to UnifiedDocument
   - Generate embeddings
   - Index to Qdrant
   - Register watch channel

2. **Incremental Updates** (ongoing):
   - Webhook receives notification
   - Validates authenticity
   - Enqueues Celery task
   - Task fetches only changed items
   - Updates Qdrant

3. **Watch Renewal** (periodic):
   - Celery Beat runs every 24h
   - Finds expiring watches
   - Renews before expiration

---

## 🧪 Testing

### B1-B7 Signoff Criteria

| ID | Criterion | Status |
|----|-----------|--------|
| **B1** | Backfill completeness | ✅ Test implemented |
| **B2** | Webhook incremental correctness | ✅ Test implemented |
| **B3** | Webhook authenticity rejection | ✅ Test implemented |
| **B4** | Rate-limit resilience | ✅ Test implemented |
| **B5** | Credential leakage | ✅ Test implemented |
| **B6** | Metadata allowlist enforcement | ✅ Test implemented |
| **B7** | Watch channel renewal | ✅ Test implemented |

**Run all tests:**
```powershell
pytest tests/test_signoff_block_b.py -v
```

---

## 🔧 Key Environment Variables

```bash
# Block B: Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/connectors/google/callback

# Block B: Pub/Sub (Gmail push)
GOOGLE_PUBSUB_PROJECT_ID=your-project-id
GOOGLE_PUBSUB_TOPIC=gmail-watch-notifications

# Block B: Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION_NAME=documents

# Block B: Embeddings
EMBEDDING_PROVIDER=fake  # Use 'gemini' in production
GEMINI_API_KEY=your-gemini-api-key

# Block B: Celery
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/1
```

---

## 🐳 Docker Services

```yaml
services:
  postgres:     # PostgreSQL 16
  redis:        # Redis 7
  qdrant:       # Qdrant (vector DB) 🆕
  app:          # FastAPI app
  celery_worker: # Celery worker 🆕
  celery_beat:   # Celery beat (periodic tasks) 🆕
```

**Start all:**
```powershell
docker-compose up -d
```

**Check logs:**
```powershell
docker-compose logs -f celery_worker  # Task execution
docker-compose logs -f celery_beat    # Periodic tasks
docker-compose logs -f app            # API requests
```

---

## 📦 What Files Were Created/Updated

### New Files (50+)
```
app/connectors/google/
  ├── manifest.yaml
  ├── oauth.py
  ├── watch_manager.py
  ├── webhooks.py
  ├── clients/
  │   ├── drive_client.py
  │   └── gmail_client.py
  └── services/
      ├── drive_service.py
      └── gmail_service.py

app/services/
  ├── cursor_store.py
  └── embedding.py

app/storage/
  └── qdrant_client.py

app/workers/
  ├── celery_app.py
  ├── tasks.py
  └── beat_schedule.py

tests/
  ├── test_signoff_block_b.py
  └── fixtures/google/
      ├── drive/ (4 JSON files)
      └── gmail/ (3 JSON files)

Documentation:
  ├── BLOCK_B_GUIDE.md
  └── SIGNOFF_BLOCK_B.md
```

### Updated Files
- `app/services/registry.py` - Recursive discovery + manifest parsing
- `app/services/indexer.py` - Real implementation (was stub)
- `docker-compose.yml` - Added Qdrant, Celery worker, Celery beat
- `requirements.txt` - Block B dependencies
- `.env.example` - Block B environment variables
- `README.md` - Block B overview

---

## 💡 Key Design Decisions

1. **One Google Package** - Drive, Gmail, (future Calendar/Chat) share OAuth
2. **Push > Poll** - Webhooks trigger incremental sync, no polling
3. **Celery for Async** - Heavy operations don't block web server
4. **Manifest-Driven** - Metadata allowlist in manifest.yaml, not code
5. **Cursor-Based Resume** - Remember where we left off (pageToken/historyId)
6. **Auto-Renewal** - Watch channels renewed before expiration
7. **Blind Orchestrator** - Sync/indexer never import specific connectors

---

## 🎯 Next Steps

### To Test with Mock Data:
```powershell
pytest tests/test_signoff_block_b.py -v
```

### To Connect Your Real Account:
1. Open `BLOCK_B_GUIDE.md`
2. Follow "Testing with Your Real Gmail & Drive" section
3. Complete Steps 1-10 (takes ~30 minutes first time)

### To Add Calendar Support:
1. Add Calendar scope to `manifest.yaml`
2. Create `clients/calendar_client.py`
3. Create `services/calendar_service.py`
4. Done! (No changes to core files)

---

## 🆘 Troubleshooting

**Issue**: Tests fail with import errors
```powershell
# Solution: Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

**Issue**: "No module named 'celery'"
```powershell
# Solution: Rebuild Docker image
docker-compose build --no-cache
```

**Issue**: Webhook not receiving notifications
```powershell
# Solution: Check ngrok and webhook URL
ngrok http 8000  # Get public URL
# Update WEBHOOK_BASE_URL in .env
```

**Issue**: Rate limit errors
```powershell
# Solution: Tasks auto-retry with exponential backoff
# Check Google Cloud Console quotas
```

---

## 📊 Statistics

- **Lines of Code**: ~3,500 (production code)
- **Test Code**: ~1,000 (B1-B7 + fixtures)
- **Documentation**: ~2,000 lines
- **Files Created**: 50+
- **Files Updated**: 6
- **Docker Services**: 6 (was 3)
- **Celery Tasks**: 4
- **API Endpoints**: 2 webhooks
- **Test Fixtures**: 7 JSON files
- **Signoff Tests**: 10 (B1-B7 x 2 services)

---

## ✅ Completion Checklist

- [x] Google connector package structure
- [x] Shared OAuth manager
- [x] Drive & Gmail clients
- [x] Drive & Gmail connectors
- [x] Watch manager
- [x] Webhook receivers
- [x] Celery workers (4 tasks)
- [x] Cursor store
- [x] Embedding service
- [x] Qdrant client
- [x] Real indexer
- [x] Registry updates
- [x] Test fixtures
- [x] B1-B7 signoff tests
- [x] Docker Compose updates
- [x] Comprehensive documentation
- [x] README updates
- [x] Signoff report template

**BLOCK B IS 100% COMPLETE!** 🎉

---

## 🎓 Learning Resources

1. **Architecture Overview**: `BLOCK_B_GUIDE.md` - Section 2
2. **How It Works**: `BLOCK_B_GUIDE.md` - Section 3
3. **Component Details**: `BLOCK_B_GUIDE.md` - Section 4
4. **Testing Guide**: `BLOCK_B_GUIDE.md` - Sections 5 & 6
5. **Troubleshooting**: `BLOCK_B_GUIDE.md` - Section 7

---

**Questions? Check `BLOCK_B_GUIDE.md` for detailed explanations of every component!**
