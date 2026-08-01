"""
Vault Client - Main implementation.
Provides secrets storage, retrieval, and rotation.
Uses Supabase Vault (pgsodium) if available, otherwise dedicated secrets table.
"""

import json
import logging
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class VaultBackend(ABC):
    """Abstract base class for vault backends"""
    
    @abstractmethod
    def get(self, key_ref: str) -> Optional[str]:
        """Retrieve a secret by key reference"""
        pass
    
    @abstractmethod
    def set(self, key_ref: str, value: str):
        """Store a secret by key reference"""
        pass
    
    @abstractmethod
    def rotate(self, key_ref: str, new_value: str):
        """Rotate a secret by key reference"""
        pass
    
    @abstractmethod
    def delete(self, key_ref: str):
        """Delete a secret by key reference"""
        pass


class PgsodiumVaultBackend(VaultBackend):
    """
    Supabase Vault backend using pgsodium.
    This is the preferred backend if pgsodium is available.
    """
    
    def __init__(self, db_client):
        """
        Initialize pgsodium vault backend.
        
        Args:
            db_client: Database client with pgsodium extension enabled
        """
        self.db_client = db_client
        self._verify_pgsodium_enabled()
    
    def _verify_pgsodium_enabled(self):
        """Verify pgsodium extension is enabled in the database"""
        try:
            result = self.db_client.fetch_one(
                "SELECT 1 FROM pg_extension WHERE extname = 'pgsodium'",
                ()
            )
            if not result:
                raise RuntimeError("pgsodium extension is not enabled")
            logger.info("pgsodium extension verified")
        except Exception as e:
            logger.error(f"Failed to verify pgsodium: {e}")
            raise RuntimeError(f"pgsodium not available: {e}")
    
    def get(self, key_ref: str) -> Optional[str]:
        """
        Retrieve a secret using pgsodium.vault.decrypt().
        
        Args:
            key_ref: The key reference identifier
            
        Returns:
            Decrypted secret value as string, or None if not found
        """
        query = """
            SELECT vault.decrypt(key) as value
            FROM vault.secrets
            WHERE key = %s
        """
        result = self.db_client.fetch_one(query, (key_ref,))
        
        if result:
            return result["value"]
        return None
    
    def set(self, key_ref: str, value: str):
        """
        Store a secret using pgsodium.vault.encrypt().
        
        Args:
            key_ref: The key reference identifier
            value: The secret value to store (will be encrypted)
        """
        query = """
            INSERT INTO vault.secrets (key, value)
            VALUES (%s, vault.encrypt(%s))
            ON CONFLICT (key) DO UPDATE SET value = vault.encrypt(%s)
        """
        self.db_client.execute(query, (key_ref, value, value))
        logger.debug(f"Stored secret for key_ref: {key_ref}")
    
    def rotate(self, key_ref: str, new_value: str):
        """
        Rotate a secret - first-class operation.
        
        Args:
            key_ref: The key reference identifier
            new_value: The new secret value
        """
        # In pgsodium, rotation is essentially an update with new encryption
        query = """
            UPDATE vault.secrets
            SET value = vault.encrypt(%s)
            WHERE key = %s
        """
        self.db_client.execute(query, (new_value, key_ref))
        logger.info(f"Rotated secret for key_ref: {key_ref}")
    
    def delete(self, key_ref: str):
        """
        Delete a secret.
        
        Args:
            key_ref: The key reference identifier
        """
        query = "DELETE FROM vault.secrets WHERE key = %s"
        self.db_client.execute(query, (key_ref,))
        logger.debug(f"Deleted secret for key_ref: {key_ref}")


class TableVaultBackend(VaultBackend):
    """
    Fallback vault backend using a dedicated secrets table.
    Used when pgsodium is not available.
    The table itself is encrypted at rest via database-level encryption.
    """
    
    def __init__(self, db_client):
        """
        Initialize table vault backend.
        
        Args:
            db_client: Database client
        """
        self.db_client = db_client
        self._ensure_secrets_table()
    
    def _ensure_secrets_table(self):
        """Ensure the secrets table exists"""
        query = """
            CREATE TABLE IF NOT EXISTS secrets (
                key_ref VARCHAR(255) PRIMARY KEY,
                value_jsonb JSONB NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_secrets_key_ref ON secrets(key_ref);
            
            COMMENT ON TABLE secrets IS 'Fallback secrets table when pgsodium not available. Encrypted at rest via DB-level encryption.';
            COMMENT ON COLUMN secrets.value_jsonb IS 'Opaque JSONB envelope - credential shape is unknown to this layer';
        """
        self.db_client.execute(query, ())
        logger.info("Secrets table verified/created")
    
    def get(self, key_ref: str) -> Optional[str]:
        """
        Retrieve a secret from the secrets table.
        
        Args:
            key_ref: The key reference identifier
            
        Returns:
            Secret value as JSON string, or None if not found
        """
        query = "SELECT value_jsonb FROM secrets WHERE key_ref = %s"
        result = self.db_client.fetch_one(query, (key_ref,))
        
        if result:
            return json.dumps(result["value_jsonb"])
        return None
    
    def set(self, key_ref: str, value: str):
        """
        Store a secret in the secrets table.
        
        Args:
            key_ref: The key reference identifier
            value: The secret value (should be JSON string envelope)
        """
        # Parse as JSON to ensure it's valid JSONB, then dump back to string for psycopg2
        value_json = json.loads(value)
        value_json_str = json.dumps(value_json)
        
        query = """
            INSERT INTO secrets (key_ref, value_jsonb, updated_at)
            VALUES (%s, %s::jsonb, CURRENT_TIMESTAMP)
            ON CONFLICT (key_ref) DO UPDATE 
            SET value_jsonb = %s::jsonb, updated_at = CURRENT_TIMESTAMP
        """
        self.db_client.execute(query, (key_ref, value_json_str, value_json_str))
        logger.debug(f"Stored secret for key_ref: {key_ref}")
    
    def rotate(self, key_ref: str, new_value: str):
        """
        Rotate a secret - first-class operation.
        
        Args:
            key_ref: The key reference identifier
            new_value: The new secret value
        """
        value_json = json.loads(new_value)
        
        query = """
            UPDATE secrets
            SET value_jsonb = %s, updated_at = CURRENT_TIMESTAMP
            WHERE key_ref = %s
        """
        self.db_client.execute(query, (key_ref, value_json))
        logger.info(f"Rotated secret for key_ref: {key_ref}")
    
    def delete(self, key_ref: str):
        """
        Delete a secret.
        
        Args:
            key_ref: The key reference identifier
        """
        query = "DELETE FROM secrets WHERE key_ref = %s"
        self.db_client.execute(query, (key_ref,))
        logger.debug(f"Deleted secret for key_ref: {key_ref}")


class VaultClient:
    """
    Vault client for secrets management.
    
    Provides a unified interface for secrets storage and retrieval.
    Automatically selects pgsodium backend if available, otherwise table backend.
    
    Credential envelopes are stored as opaque JSONB - this layer never parses
    the internal structure of credentials (OAuth tokens, API keys, etc.).
    """
    
    def __init__(self, db_client, use_pgsodium: bool = True):
        """
        Initialize VaultClient.
        
        Args:
            db_client: Database client
            use_pgsodium: If True, attempt to use pgsodium; fallback to table if unavailable
        """
        self.db_client = db_client
        self.backend: VaultBackend
        
        if use_pgsodium:
            try:
                self.backend = PgsodiumVaultBackend(db_client)
                logger.info("Using pgsodium vault backend")
            except RuntimeError:
                logger.warning("pgsodium not available, falling back to table backend")
                self.backend = TableVaultBackend(db_client)
        else:
            self.backend = TableVaultBackend(db_client)
            logger.info("Using table vault backend (pgsodium disabled)")
    
    def get(self, key_ref: str) -> Optional[str]:
        """
        Retrieve a secret by key reference.
        
        Args:
            key_ref: The key reference identifier (e.g., "tenant_123_creds")
            
        Returns:
            Secret value as JSON string, or None if not found
        """
        return self.backend.get(key_ref)
    
    def set(self, key_ref: str, value: str):
        """
        Store a secret by key reference.
        
        Args:
            key_ref: The key reference identifier
            value: The secret value (should be JSON string envelope)
        """
        self.backend.set(key_ref, value)
    
    def rotate(self, key_ref: str, new_value: str):
        """
        Rotate a secret - first-class operation.
        This is critical for D4 signoff (key rotation with zero downtime).
        
        Args:
            key_ref: The key reference identifier
            new_value: The new secret value
        """
        self.backend.rotate(key_ref, new_value)
    
    def delete(self, key_ref: str):
        """
        Delete a secret by key reference.
        
        Args:
            key_ref: The key reference identifier
        """
        self.backend.delete(key_ref)
    
    def store_credential_envelope(self, key_ref: str, credential_data: Dict[str, Any]):
        """
        Store a credential envelope.
        
        This is a convenience method for storing credential data as JSONB.
        The internal structure of credential_data is opaque to this layer.
        
        Args:
            key_ref: The key reference identifier
            credential_data: Dictionary containing credential data (OAuth tokens, API keys, etc.)
        """
        envelope = json.dumps(credential_data)
        self.set(key_ref, envelope)
    
    def get_credential_envelope(self, key_ref: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a credential envelope.
        
        Args:
            key_ref: The key reference identifier
            
        Returns:
            Dictionary containing credential data, or None if not found
        """
        value = self.get(key_ref)
        if value:
            return json.loads(value)
        return None
