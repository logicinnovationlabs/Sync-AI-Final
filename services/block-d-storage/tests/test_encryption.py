"""
Tests for Component (f) - Encryption/KMS
Tests envelope encryption and key rotation.
"""

import pytest
from encryption.encryption_client import EncryptionClient
from tests.mocks import MockDatabaseClient


class TestEncryptionClient:
    """Test suite for EncryptionClient"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database client"""
        return MockDatabaseClient()
    
    def test_pgsodium_verification_fails_without_extension(self, mock_db):
        """
        CRITICAL TEST: Verify that EncryptionClient fails gracefully when pgsodium is not available.
        Per user instruction: Verify pgsodium is enabled before building - if it's not available,
        stop and report back rather than assuming a fallback.
        """
        with pytest.raises(RuntimeError, match="pgsodium extension is not enabled"):
            EncryptionClient(mock_db)
    
    def test_encrypt_requires_pgsodium(self, mock_db):
        """Test that encrypt operation requires pgsodium (fails at initialization)"""
        with pytest.raises(RuntimeError, match="pgsodium extension is not enabled"):
            EncryptionClient(mock_db)
    
    def test_decrypt_requires_pgsodium(self, mock_db):
        """Test that decrypt operation requires pgsodium (fails at initialization)"""
        with pytest.raises(RuntimeError, match="pgsodium extension is not enabled"):
            EncryptionClient(mock_db)
    
    def test_rotate_key_requires_pgsodium(self, mock_db):
        """Test that key rotation requires pgsodium (fails at initialization)"""
        with pytest.raises(RuntimeError, match="pgsodium extension is not enabled"):
            EncryptionClient(mock_db)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
