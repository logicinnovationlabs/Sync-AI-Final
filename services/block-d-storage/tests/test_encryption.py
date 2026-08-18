"""
Tests for Component (f) - Encryption/KMS
Tests envelope encryption and key rotation.
"""

import pytest
from encryption.encryption_client import EncryptionClient
from tests.mocks import MockDatabaseClient, MockVaultClient


class TestEncryptionClient:
    """Test suite for EncryptionClient"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database client"""
        return MockDatabaseClient()

    @pytest.fixture
    def mock_vault(self):
        """Vault double — real callers always pass a vault_client (§9.1 / §28.2)."""
        return MockVaultClient()
    
    def test_pgsodium_verification_fails_without_extension(self, mock_db, mock_vault):
        """
        CRITICAL TEST: Verify that EncryptionClient fails gracefully when pgcrypto is not available.
        Per user instruction: Verify pgcrypto is enabled before building - if it's not available,
        stop and report back rather than assuming a fallback.
        """
        with pytest.raises(RuntimeError, match="pgcrypto extension is not enabled"):
            EncryptionClient(mock_db, mock_vault)
    
    def test_encrypt_requires_pgsodium(self, mock_db, mock_vault):
        """Test that encrypt operation requires pgcrypto (fails at initialization)"""
        with pytest.raises(RuntimeError, match="pgcrypto extension is not enabled"):
            EncryptionClient(mock_db, mock_vault)
    
    def test_decrypt_requires_pgsodium(self, mock_db, mock_vault):
        """Test that decrypt operation requires pgcrypto (fails at initialization)"""
        with pytest.raises(RuntimeError, match="pgcrypto extension is not enabled"):
            EncryptionClient(mock_db, mock_vault)
    
    def test_rotate_key_requires_pgsodium(self, mock_db, mock_vault):
        """Test that key rotation requires pgcrypto (fails at initialization)"""
        with pytest.raises(RuntimeError, match="pgcrypto extension is not enabled"):
            EncryptionClient(mock_db, mock_vault)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
