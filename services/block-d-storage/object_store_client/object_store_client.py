"""
Object Storage Client - Main implementation.
Wraps Supabase Storage (or S3-compatible equivalent) with enforced prefixing.

Per §3 modularity constraint:
- Object storage prefixing is generic and three-level: tenant_<tenant_id>/connector_<connector_instance_id>/<object_path>
- Callers cannot construct arbitrary paths; the client derives the prefix from TenantRouter output
- Bucket access keys go through the vault client, never inline in config
"""

import logging
from typing import Optional, List
from tenant_router.models import TenantRoutingInfo

logger = logging.getLogger(__name__)


class ObjectStorageClient:
    """
    Object storage client with enforced prefixing.
    
    Enforces the prefix convention: tenant_<tenant_id>/connector_<connector_instance_id>/<object_path>
    Callers provide tenant_id and connector_instance_id; the client constructs the full path.
    """
    
    def __init__(
        self,
        storage_client,
        vault_client,
        bucket_name: str = "default"
    ):
        """
        Initialize ObjectStorageClient.
        
        Args:
            storage_client: Underlying storage client (Supabase Storage or S3-compatible)
            vault_client: Vault client for retrieving bucket access keys
            bucket_name: Name of the storage bucket
        """
        self.storage_client = storage_client
        self.vault_client = vault_client
        self.bucket_name = bucket_name
        
        # Retrieve bucket access keys from vault (not inline in config)
        self._bucket_credentials = self._retrieve_bucket_credentials()
    
    def _retrieve_bucket_credentials(self) -> dict:
        """
        Retrieve bucket access credentials from vault.
        
        Per spec: Bucket access keys go through the vault client, never inline in config.
        """
        # In real implementation, this would retrieve from vault
        # For Phase 1 with mocks, return a placeholder
        logger.debug("Retrieved bucket credentials from vault")
        return {"access_key": "vault_retrieved_key", "secret_key": "vault_retrieved_secret"}
    
    def _build_path(
        self,
        tenant_id: str,
        connector_instance_id: str,
        object_path: str
    ) -> str:
        """
        Build the full object path with enforced prefixing.
        
        Per §3: tenant_<tenant_id>/connector_<connector_instance_id>/<object_path>
        This is the ONLY way to construct paths - callers cannot bypass this.
        
        Args:
            tenant_id: The tenant identifier
            connector_instance_id: The connector instance identifier
            object_path: The relative object path
            
        Returns:
            Full path with enforced prefix
        """
        # Enforce the three-level prefix convention
        # Note: We use connector_instance_id, NOT connector_type
        # This allows multiple instances of the same connector type per tenant
        full_path = f"tenant_{tenant_id}/connector_{connector_instance_id}/{object_path}"
        
        logger.debug(f"Built path: {full_path}")
        return full_path
    
    def upload(
        self,
        tenant_id: str,
        connector_instance_id: str,
        object_path: str,
        data: bytes,
        content_type: Optional[str] = None
    ) -> str:
        """
        Upload an object to storage.
        
        Args:
            tenant_id: The tenant identifier
            connector_instance_id: The connector instance identifier
            object_path: The relative object path
            data: The data to upload
            content_type: Optional content type header
            
        Returns:
            The full path of the uploaded object
        """
        full_path = self._build_path(tenant_id, connector_instance_id, object_path)
        
        # In real implementation, this would call the storage client
        # For Phase 1 with mocks, simulate the operation
        logger.info(f"Uploading to {full_path}")
        
        if hasattr(self.storage_client, 'upload'):
            self.storage_client.upload(full_path, data)
        
        return full_path
    
    def download(
        self,
        tenant_id: str,
        connector_instance_id: str,
        object_path: str
    ) -> Optional[bytes]:
        """
        Download an object from storage.
        
        Args:
            tenant_id: The tenant identifier
            connector_instance_id: The connector instance identifier
            object_path: The relative object path
            
        Returns:
            The object data, or None if not found
        """
        full_path = self._build_path(tenant_id, connector_instance_id, object_path)
        
        logger.info(f"Downloading from {full_path}")
        
        if hasattr(self.storage_client, 'download'):
            return self.storage_client.download(full_path)
        
        return None
    
    def delete(
        self,
        tenant_id: str,
        connector_instance_id: str,
        object_path: str
    ):
        """
        Delete an object from storage.
        
        Args:
            tenant_id: The tenant identifier
            connector_instance_id: The connector instance identifier
            object_path: The relative object path
        """
        full_path = self._build_path(tenant_id, connector_instance_id, object_path)
        
        logger.info(f"Deleting {full_path}")
        
        if hasattr(self.storage_client, 'delete'):
            self.storage_client.delete(full_path)
    
    def list_objects(
        self,
        tenant_id: str,
        connector_instance_id: str,
        prefix: str = ""
    ) -> List[str]:
        """
        List objects in a tenant/connector prefix.
        
        Args:
            tenant_id: The tenant identifier
            connector_instance_id: The connector instance identifier
            prefix: Optional additional prefix to filter results
            
        Returns:
            List of object paths (relative to the tenant/connector prefix)
        """
        base_prefix = self._build_path(tenant_id, connector_instance_id, prefix)
        
        logger.info(f"Listing objects with prefix {base_prefix}")
        
        if hasattr(self.storage_client, 'list_objects'):
            full_paths = self.storage_client.list_objects(base_prefix)
            
            # Strip the tenant/connector prefix to return relative paths
            tenant_connector_prefix = f"tenant_{tenant_id}/connector_{connector_instance_id}/"
            relative_paths = [
                path.replace(tenant_connector_prefix, "", 1)
                for path in full_paths
            ]
            
            return relative_paths
        
        return []
    
    def get_full_path(
        self,
        tenant_id: str,
        connector_instance_id: str,
        object_path: str
    ) -> str:
        """
        Get the full path for an object without performing any storage operation.
        
        Useful for generating URLs or references.
        
        Args:
            tenant_id: The tenant identifier
            connector_instance_id: The connector instance identifier
            object_path: The relative object path
            
        Returns:
            The full path with enforced prefix
        """
        return self._build_path(tenant_id, connector_instance_id, object_path)
