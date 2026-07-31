# Connectors Directory

**Status:** EMPTY (Block A) — Block B will populate this directory.

---

## Purpose

This directory will contain all source connectors (Google Drive, Slack, GitHub, etc.).

Each connector is a self-contained module that implements the `BaseConnector` interface.

---

## How to Add a Connector (Block B)

### 1. Create Connector Directory

```
app/connectors/
├── __init__.py (already exists, leave empty)
└── google_drive/
    ├── __init__.py
    ├── connector.py
    ├── client.py (optional)
    └── config.py (optional)
```

### 2. Implement BaseConnector

```python
# app/connectors/google_drive/connector.py

from typing import List, Dict, Any, Optional
from datetime import datetime
from app.core.base_connector import (
    BaseConnector,
    TokenStore,
    DeltaResult,
    DeletionResult,
    UnifiedDocument,
)


class GoogleDriveConnector(BaseConnector):
    """Google Drive connector implementation."""

    def get_source_type(self) -> str:
        """Return 'google_drive'."""
        return "google_drive"

    async def get_valid_token(self) -> str:
        """
        Refresh OAuth token if needed and return valid access token.
        
        Uses self.token_store to persist refresh tokens.
        """
        # Implement OAuth refresh logic
        token_data = self.token_store.get_token("google_drive_refresh")
        # ... refresh logic ...
        return access_token

    async def fetch_delta(
        self,
        since: datetime,
        cursor: Optional[str],
    ) -> DeltaResult:
        """
        Fetch documents changed since `since`.
        
        Args:
            since: Fetch docs modified after this timestamp
            cursor: Pagination cursor (None for first page)
            
        Returns:
            DeltaResult with documents, next_cursor, has_more.
        """
        # Call Google Drive API
        # GET /drive/v3/files?q=modifiedTime > since&pageToken=cursor
        
        documents = [...]  # Raw Google Drive file objects
        next_cursor = response.get("nextPageToken")
        has_more = next_cursor is not None
        
        return DeltaResult(
            documents=documents,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def fetch_deleted_ids(
        self,
        since: datetime,
        cursor: Optional[str],
    ) -> DeletionResult:
        """
        Fetch IDs of deleted files.
        
        Google Drive API supports this via changes.list with includeRemoved=true.
        """
        # Call Google Drive API
        # GET /drive/v3/changes?includeRemoved=true&startPageToken=cursor
        
        deleted_ids = [...]  # List of file IDs
        next_cursor = response.get("nextPageToken")
        has_more = next_cursor is not None
        
        return DeletionResult(
            deleted_ids=deleted_ids,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def transform(
        self,
        raw_documents: List[Dict[str, Any]],
    ) -> List[UnifiedDocument]:
        """
        Transform Google Drive files to UnifiedDocument format.
        
        Args:
            raw_documents: Google Drive file objects
            
        Returns:
            List of UnifiedDocument instances.
        """
        unified_docs = []
        
        for raw_doc in raw_documents:
            doc = UnifiedDocument(
                id=raw_doc["id"],
                title=raw_doc["name"],
                content=await self._extract_content(raw_doc),
                source_type="google_drive",
                url=raw_doc["webViewLink"],
                permissions=self._extract_permissions(raw_doc),
                created_at=datetime.fromisoformat(raw_doc["createdTime"]),
                updated_at=datetime.fromisoformat(raw_doc["modifiedTime"]),
                source_updated_at=datetime.fromisoformat(raw_doc["modifiedTime"]),
                structured_metadata={
                    "mime_type": raw_doc.get("mimeType"),
                    "size": raw_doc.get("size"),
                    "owners": raw_doc.get("owners", []),
                },
            )
            unified_docs.append(doc)
        
        return unified_docs

    async def _extract_content(self, file_obj: Dict) -> str:
        """Download and extract text content from a Google Drive file."""
        # Implement based on mime type (docs, sheets, slides, etc.)
        pass

    def _extract_permissions(self, file_obj: Dict) -> List[str]:
        """
        Extract permissions from Google Drive file object.
        
        Returns:
            List of permission strings: ["user:alice@example.com", "group:team@example.com"]
        """
        permissions = []
        for perm in file_obj.get("permissions", []):
            if perm["type"] == "user":
                permissions.append(f"user:{perm['emailAddress']}")
            elif perm["type"] == "group":
                permissions.append(f"group:{perm['emailAddress']}")
            elif perm["type"] == "domain":
                permissions.append(f"domain:{perm['domain']}")
        return permissions
```

### 3. That's It!

The `ConnectorRegistry` auto-discovers your connector via reflection.

**No changes to `sync.py`, `indexer.py`, or any core file needed.**

---

## Connector Contract (BaseConnector)

Every connector must implement:

### Required Methods

1. **`get_source_type() -> str`**
   - Return unique source identifier (e.g., "google_drive", "slack")

2. **`get_valid_token() -> str`**
   - Return a valid OAuth access token
   - Handle refresh logic internally
   - Use `self.token_store` to persist refresh tokens

3. **`fetch_delta(since, cursor) -> DeltaResult`**
   - Fetch documents modified after `since`
   - Support pagination via `cursor`
   - Return `DeltaResult(documents, next_cursor, has_more)`

4. **`fetch_deleted_ids(since, cursor) -> DeletionResult`**
   - Fetch IDs of deleted documents
   - Return `DeletionResult(deleted_ids, next_cursor, has_more)`
   - Raise `NotImplementedError` if source doesn't support deletion tracking

5. **`transform(raw_documents) -> List[UnifiedDocument]`**
   - Transform raw source objects to `UnifiedDocument` format
   - Extract permissions (must be prefixed "user:" or "group:")
   - Populate all required fields

---

## UnifiedDocument Schema

```python
class UnifiedDocument(BaseModel):
    id: str                         # Globally unique doc ID
    title: str                      # Document title
    content: str                    # Full text content
    source_type: str                # Connector type (e.g., "google_drive")
    url: str                        # Deep link back to source
    permissions: List[str]          # ["user:alice@example.com", "group:team@example.com"]
    created_at: datetime            # When doc was created
    updated_at: datetime            # When doc was last modified (by us)
    source_updated_at: datetime     # Source's own last-modified timestamp (CRITICAL for delta cursors)
    structured_metadata: Dict       # Source-specific metadata (optional)
```

---

## Orchestrator Usage (Already Implemented in Block A)

```python
from app.services.sync import sync_orchestrator

# The orchestrator will:
# 1. Get connector from registry (no name imports!)
# 2. Run deletion pass first (security priority)
# 3. Run delta pass second
# 4. Transform to UnifiedDocument
# 5. Pass to indexer (Block C/E implement fully)

await sync_orchestrator.run_sync(
    source_type="google_drive",  # Auto-discovered by registry
    tenant_id=tenant_id,
    config=connector_config,
    token_store=secure_token_store,
    last_sync=last_sync_timestamp,
)
```

---

## Testing Your Connector

```python
# tests/test_google_drive_connector.py

import pytest
from datetime import datetime, timezone
from app.connectors.google_drive.connector import GoogleDriveConnector

@pytest.mark.asyncio
async def test_google_drive_fetch_delta():
    connector = GoogleDriveConnector(
        config={"client_id": "...", "client_secret": "..."},
        token_store=mock_token_store,
    )
    
    result = await connector.fetch_delta(
        since=datetime(2024, 1, 1, tzinfo=timezone.utc),
        cursor=None,
    )
    
    assert len(result.documents) > 0
    assert result.has_more is not None


@pytest.mark.asyncio
async def test_google_drive_transform():
    connector = GoogleDriveConnector(config={}, token_store=mock_token_store)
    
    raw_docs = [{
        "id": "file123",
        "name": "Test Doc",
        "mimeType": "application/vnd.google-apps.document",
        "createdTime": "2024-01-01T00:00:00Z",
        "modifiedTime": "2024-01-02T00:00:00Z",
        "webViewLink": "https://drive.google.com/...",
        "permissions": [{"type": "user", "emailAddress": "alice@example.com"}],
    }]
    
    unified = await connector.transform(raw_docs)
    
    assert len(unified) == 1
    assert unified[0].source_type == "google_drive"
    assert unified[0].permissions == ["user:alice@example.com"]
```

---

## Available Token Store

The orchestrator provides a `TokenStore` protocol:

```python
class TokenStore(Protocol):
    def get_token(self, key: str) -> Optional[Dict[str, Any]]: ...
    def set_token(self, key: str, token_data: Dict[str, Any]) -> None: ...
```

Use this to persist OAuth refresh tokens:

```python
async def get_valid_token(self) -> str:
    # Get refresh token
    token_data = self.token_store.get_token("google_drive_refresh")
    
    if not token_data:
        raise Exception("No refresh token stored")
    
    # Refresh access token
    new_access_token = await self._refresh_oauth_token(token_data["refresh_token"])
    
    # Update stored token
    self.token_store.set_token("google_drive_refresh", {
        "access_token": new_access_token,
        "refresh_token": token_data["refresh_token"],
        "expires_at": ...,
    })
    
    return new_access_token
```

---

## Common Patterns

### OAuth Refresh

```python
async def _refresh_oauth_token(self, refresh_token: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth.provider.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.config["client_id"],
                "client_secret": self.config["client_secret"],
            },
        )
        data = response.json()
        return data["access_token"]
```

### Pagination

```python
async def fetch_delta(self, since, cursor):
    url = f"https://api.provider.com/files?modifiedAfter={since.isoformat()}"
    if cursor:
        url += f"&pageToken={cursor}"
    
    response = await self._api_call(url)
    data = response.json()
    
    return DeltaResult(
        documents=data["files"],
        next_cursor=data.get("nextPageToken"),
        has_more="nextPageToken" in data,
    )
```

### Permission Extraction

```python
def _extract_permissions(self, raw_doc: Dict) -> List[str]:
    permissions = []
    
    for perm in raw_doc.get("permissions", []):
        if perm["type"] == "user":
            permissions.append(f"user:{perm['email']}")
        elif perm["type"] == "group":
            permissions.append(f"group:{perm['group_id']}")
    
    # Always include owner
    owner_email = raw_doc.get("owner", {}).get("email")
    if owner_email:
        permissions.append(f"user:{owner_email}")
    
    return list(set(permissions))  # Deduplicate
```

---

## Next Steps

1. Implement your connector in `app/connectors/<source_name>/`
2. Write unit tests in `tests/test_<source_name>_connector.py`
3. Test with the orchestrator:
   ```python
   await sync_orchestrator.run_sync(
       source_type=your_source_type,
       tenant_id=test_tenant_id,
       config=your_config,
       token_store=token_store,
   )
   ```
4. Verify in logs that deletion pass runs before delta pass
5. Verify `UnifiedDocument` objects are created correctly

---

## Questions?

Consult:
- `app/core/base_connector.py` — Full BaseConnector interface
- `app/services/sync.py` — Orchestrator implementation
- `README.md` — Full project documentation
- Architecture PDF — Section on Block B
