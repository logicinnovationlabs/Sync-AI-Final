"""
Tests for Component (b) - Vault Client
Tests secrets storage, retrieval, and rotation with both backends.
"""

import pytest
import json
from vault_client.vault_client import VaultClient, PgsodiumVaultBackend, TableVaultBackend
from tests.mocks import MockDatabaseClient


class TestTableVaultBackend:
    """Test suite for TableVaultBackend (fallback)"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database client"""
        return MockDatabaseClient()
    
    @pytest.fixture
    def backend(self, mock_db):
        """TableVaultBackend instance"""
        return TableVaultBackend(mock_db)
    
    def test_set_and_get(self, backend):
        """Test basic set and get operations"""
        backend.set("test_key", '{"secret": "value"}')
        
        result = backend.get("test_key")
        assert result is not None
        data = json.loads(result)
        assert data["secret"] == "value"
    
    def test_get_nonexistent(self, backend):
        """Test get with non-existent key returns None"""
        result = backend.get("nonexistent_key")
        assert result is None
    
    def test_rotate(self, backend):
        """Test rotation operation"""
        backend.set("test_key", '{"secret": "old_value"}')
        
        backend.rotate("test_key", '{"secret": "new_value"}')
        
        result = backend.get("test_key")
        data = json.loads(result)
        assert data["secret"] == "new_value"
    
    def test_delete(self, backend):
        """Test delete operation"""
        backend.set("test_key", '{"secret": "value"}')
        
        backend.delete("test_key")
        
        result = backend.get("test_key")
        assert result is None
    
    def test_set_updates_existing(self, backend):
        """Test that set updates existing key"""
        backend.set("test_key", '{"secret": "old_value"}')
        backend.set("test_key", '{"secret": "new_value"}')
        
        result = backend.get("test_key")
        data = json.loads(result)
        assert data["secret"] == "new_value"
    
    def test_opaque_credential_envelope(self, backend):
        """
        CRITICAL TEST: Verify credential envelopes are stored as opaque JSONB.
        This layer should not parse or validate the internal structure.
        """
        # OAuth token envelope
        oauth_envelope = json.dumps({
            "access_token": "ya29.a0AfH6...",
            "refresh_token": "1//0g...",
            "token_type": "Bearer",
            "expiry": "2026-07-31T12:00:00Z"
        })
        
        # API key envelope
        api_key_envelope = json.dumps({
            "api_key": "sk-1234567890abcdef",
            "key_id": "key_abc123"
        })
        
        # Service account JSON envelope
        service_account_envelope = json.dumps({
            "type": "service_account",
            "project_id": "my-project",
            "private_key_id": "key123",
            "private_key": "-----BEGIN PRIVATE KEY-----\n...",
            "client_email": "service@my-project.iam.gserviceaccount.com"
        })
        
        # Store all three - backend should not care about the structure
        backend.set("oauth_creds", oauth_envelope)
        backend.set("api_key_creds", api_key_envelope)
        backend.set("service_account_creds", service_account_envelope)
        
        # Retrieve and verify they're stored correctly
        oauth_result = json.loads(backend.get("oauth_creds"))
        assert oauth_result["token_type"] == "Bearer"
        
        api_result = json.loads(backend.get("api_key_creds"))
        assert api_result["api_key"] == "sk-1234567890abcdef"
        
        sa_result = json.loads(backend.get("service_account_creds"))
        assert sa_result["type"] == "service_account"


class TestVaultClient:
    """Test suite for VaultClient unified interface"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database client"""
        return MockDatabaseClient()
    
    @pytest.fixture
    def vault_client(self, mock_db):
        """VaultClient with table backend (pgsodium disabled for testing)"""
        return VaultClient(mock_db, use_pgsodium=False)
    
    def test_get_and_set(self, vault_client):
        """Test basic get and set"""
        vault_client.set("test_key", '{"secret": "value"}')
        
        result = vault_client.get("test_key")
        assert result is not None
        
        data = json.loads(result)
        assert data["secret"] == "value"
    
    def test_rotate(self, vault_client):
        """Test rotation through VaultClient"""
        vault_client.set("test_key", '{"secret": "old_value"}')
        
        vault_client.rotate("test_key", '{"secret": "new_value"}')
        
        result = vault_client.get("test_key")
        data = json.loads(result)
        assert data["secret"] == "new_value"
    
    def test_delete(self, vault_client):
        """Test delete through VaultClient"""
        vault_client.set("test_key", '{"secret": "value"}')
        vault_client.delete("test_key")
        
        result = vault_client.get("test_key")
        assert result is None
    
    def test_store_credential_envelope(self, vault_client):
        """Test convenience method for credential envelopes"""
        credential_data = {
            "access_token": "ya29.a0AfH6...",
            "refresh_token": "1//0g...",
            "token_type": "Bearer"
        }
        
        vault_client.store_credential_envelope("tenant_123_creds", credential_data)
        
        retrieved = vault_client.get_credential_envelope("tenant_123_creds")
        assert retrieved is not None
        assert retrieved["access_token"] == "ya29.a0AfH6..."
        assert retrieved["token_type"] == "Bearer"
    
    def test_get_credential_envelope_nonexistent(self, vault_client):
        """Test get_credential_envelope with non-existent key"""
        result = vault_client.get_credential_envelope("nonexistent")
        assert result is None
    
    def test_rotation_is_first_class_operation(self, vault_client):
        """
        CRITICAL TEST: Verify rotation is a first-class operation, not an afterthought.
        This is required for D4 signoff.
        """
        # Store initial credential
        initial_creds = {"api_key": "old_key_12345"}
        vault_client.store_credential_envelope("tenant_creds", initial_creds)
        
        # Rotate to new credential
        rotated_creds = {"api_key": "new_key_67890"}
        vault_client.rotate("tenant_creds", json.dumps(rotated_creds))
        
        # Verify rotation succeeded
        retrieved = vault_client.get_credential_envelope("tenant_creds")
        assert retrieved["api_key"] == "new_key_67890"
        assert retrieved["api_key"] != "old_key_12345"


class TestPgsodiumVaultBackend:
    """Test suite for PgsodiumVaultBackend (requires real pgsodium)"""
    
    def test_pgsodium_not_available_in_mock(self):
        """
        Test that pgsodium backend fails gracefully when not available.
        This is expected in Phase 1 testing with mocks.
        """
        mock_db = MockDatabaseClient()
        
        with pytest.raises(RuntimeError, match="pgsodium not available"):
            PgsodiumVaultBackend(mock_db)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
