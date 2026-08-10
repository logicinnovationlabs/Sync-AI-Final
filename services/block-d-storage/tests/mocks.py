"""
Mock clients for Block Z dependencies (Phase 1 testing).
These will be replaced with real implementations in Phase 2.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import json


class MockRow:
    """Mock database row"""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def __getitem__(self, key):
        return getattr(self, key, None)


class MockDatabaseClient:
    """Mock database client for Phase 1 testing"""
    
    def __init__(self):
        self._tenants: Dict[str, Dict[str, Any]] = {}
        self._schemas: Dict[str, List[str]] = {}  # schema_name -> list of tables
        self._secrets: Dict[str, Dict[str, Any]] = {}  # key_ref -> secret data
    
    def create_tenant(self, tenant_data: Dict[str, Any]):
        """Create a tenant in the mock database"""
        self._tenants[tenant_data["tenant_id"]] = tenant_data
    
    def fetch_one(self, query: str, params: tuple) -> Optional[MockRow]:
        """Mock fetch_one operation"""
        if "tenants" in query and "WHERE tenant_id" in query:
            tenant_id = params[0]
            if tenant_id in self._tenants:
                data = self._tenants[tenant_id]
                return MockRow(
                    tenant_id=data["tenant_id"],
                    tenancy_mode=data["tenancy_mode"],
                    db_schema_name=data["db_schema_name"],
                    object_store_prefix=data["object_store_prefix"],
                    secrets_key_ref=data["secrets_key_ref"],
                    created_at=data.get("created_at", datetime.now(timezone.utc)),
                    status=data.get("status", "active")
                )
        elif "secrets" in query and "WHERE key_ref" in query:
            key_ref = params[0]
            if key_ref in self._secrets:
                # Return the value as value_jsonb field (dict) for vault client
                # The vault_client.set() already converts to JSON string, so we need to parse it back
                # to simulate how the real database returns JSONB as a dict
                value = self._secrets[key_ref]
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except:
                        value = {}
                return MockRow(value_jsonb=value)
        elif "pg_extension" in query and "pgsodium" in query:
            # Return None to indicate pgsodium not available
            return None
        return None
    
    def execute(self, query: str, params: tuple):
        """Mock execute operation"""
        if "CREATE SCHEMA" in query:
            # Extract schema name from query like "CREATE SCHEMA IF NOT EXISTS tenant_123"
            parts = query.split()
            schema_name = parts[-1].rstrip(";")
            if schema_name not in self._schemas:
                self._schemas[schema_name] = []
        elif "INSERT INTO tenants" in query:
            # Handle tenant insertion
            if len(params) >= 5:
                tenant_id = params[0]
                self._tenants[tenant_id] = {
                    "tenant_id": params[0],
                    "tenancy_mode": params[1],
                    "db_schema_name": params[2],
                    "object_store_prefix": params[3],
                    "secrets_key_ref": params[4],
                    "status": params[5] if len(params) > 5 else "active"
                }
        elif "CREATE TABLE IF NOT EXISTS secrets" in query:
            # Mock table creation - no-op
            pass
        elif "INSERT INTO secrets" in query or "UPDATE secrets" in query:
            # Handle secrets insert/update
            if len(params) >= 2:
                key_ref = params[0]
                value_json = params[1]
                # Store as-is to simulate JSONB storage (database handles JSONB conversion)
                # The vault_client already converts to JSON string before calling this
                self._secrets[key_ref] = value_json
            elif len(params) == 2 and isinstance(params[0], str) and isinstance(params[1], dict):
                # Handle UPDATE with (key_ref, value_json) order
                key_ref = params[0]
                value_json = params[1]
                self._secrets[key_ref] = value_json
        elif "DELETE FROM secrets" in query:
            key_ref = params[0]
            if key_ref in self._secrets:
                del self._secrets[key_ref]
    
    def fetch_all(self, query: str, params: tuple) -> List[MockRow]:
        """Mock fetch_all operation"""
        if "tenants" in query:
            return [
                MockRow(
                    tenant_id=data["tenant_id"],
                    tenancy_mode=data["tenancy_mode"],
                    db_schema_name=data["db_schema_name"],
                    object_store_prefix=data["object_store_prefix"],
                    secrets_key_ref=data["secrets_key_ref"],
                    created_at=data.get("created_at", datetime.now(timezone.utc)),
                    status=data.get("status", "active")
                )
                for data in self._tenants.values()
            ]
        return []


class MockVaultClient:
    """Mock vault client for Phase 1 testing"""
    
    def __init__(self):
        self._secrets: Dict[str, str] = {}
    
    def set(self, key_ref: str, value: str):
        """Store a secret"""
        self._secrets[key_ref] = value
    
    def get(self, key_ref: str) -> Optional[str]:
        """Retrieve a secret"""
        return self._secrets.get(key_ref)
    
    def rotate(self, key_ref: str, new_value: str):
        """Rotate a secret"""
        if key_ref in self._secrets:
            self._secrets[key_ref] = new_value
        else:
            raise KeyError(f"Key ref {key_ref} not found")


class MockStorageClient:
    """Mock storage client for Phase 1 testing"""
    
    def __init__(self):
        self._objects: Dict[str, bytes] = {}
    
    def upload(self, path: str, data: bytes):
        """Upload an object"""
        self._objects[path] = data
    
    def download(self, path: str) -> Optional[bytes]:
        """Download an object"""
        return self._objects.get(path)
    
    def delete(self, path: str):
        """Delete an object"""
        if path in self._objects:
            del self._objects[path]
    
    def list_objects(self, prefix: str) -> List[str]:
        """List objects with given prefix"""
        return [path for path in self._objects.keys() if path.startswith(prefix)]
