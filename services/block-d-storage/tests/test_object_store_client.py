"""
Tests for Component (d) - Object Storage Client
Tests enforced prefixing and vault credential retrieval.
"""

import pytest
from object_store_client.object_store_client import ObjectStorageClient
from tests.mocks import MockStorageClient, MockDatabaseClient
from vault_client.vault_client import VaultClient


class TestObjectStorageClient:
    """Test suite for ObjectStorageClient"""
    
    @pytest.fixture
    def mock_storage(self):
        """Mock storage client"""
        return MockStorageClient()
    
    @pytest.fixture
    def mock_db(self):
        """Mock database client"""
        return MockDatabaseClient()
    
    @pytest.fixture
    def mock_vault(self, mock_db):
        """Mock vault client"""
        return VaultClient(mock_db, use_pgsodium=False)
    
    @pytest.fixture
    def storage_client(self, mock_storage, mock_vault):
        """ObjectStorageClient instance"""
        return ObjectStorageClient(mock_storage, mock_vault)
    
    def test_upload(self, storage_client, mock_storage):
        """Test uploading an object"""
        data = b"test data"
        
        full_path = storage_client.upload(
            tenant_id="123",
            connector_instance_id="github_1",
            object_path="file.txt",
            data=data
        )
        
        assert full_path == "tenant_123/connector_github_1/file.txt"
        assert mock_storage.download(full_path) == data
    
    def test_download(self, storage_client, mock_storage):
        """Test downloading an object"""
        data = b"test data"
        storage_client.upload(
            tenant_id="123",
            connector_instance_id="github_1",
            object_path="file.txt",
            data=data
        )
        
        downloaded = storage_client.download(
            tenant_id="123",
            connector_instance_id="github_1",
            object_path="file.txt"
        )
        
        assert downloaded == data
    
    def test_delete(self, storage_client, mock_storage):
        """Test deleting an object"""
        data = b"test data"
        storage_client.upload(
            tenant_id="123",
            connector_instance_id="github_1",
            object_path="file.txt",
            data=data
        )
        
        storage_client.delete(
            tenant_id="123",
            connector_instance_id="github_1",
            object_path="file.txt"
        )
        
        downloaded = storage_client.download(
            tenant_id="123",
            connector_instance_id="github_1",
            object_path="file.txt"
        )
        
        assert downloaded is None
    
    def test_list_objects(self, storage_client, mock_storage):
        """Test listing objects"""
        # Upload multiple objects
        storage_client.upload(
            tenant_id="123",
            connector_instance_id="github_1",
            object_path="file1.txt",
            data=b"data1"
        )
        storage_client.upload(
            tenant_id="123",
            connector_instance_id="github_1",
            object_path="file2.txt",
            data=b"data2"
        )
        
        objects = storage_client.list_objects(
            tenant_id="123",
            connector_instance_id="github_1"
        )
        
        assert set(objects) == {"file1.txt", "file2.txt"}
    
    def test_enforced_prefixing(self, storage_client):
        """
        CRITICAL TEST: Verify enforced prefixing.
        Per §3: tenant_<tenant_id>/connector_<connector_instance_id>/<object_path>
        Callers cannot construct arbitrary paths.
        """
        full_path = storage_client.get_full_path(
            tenant_id="123",
            connector_instance_id="slack_1",
            object_path="messages/123.json"
        )
        
        assert full_path == "tenant_123/connector_slack_1/messages/123.json"
    
    def test_prefix_uses_connector_instance_id_not_type(self, storage_client):
        """
        CRITICAL TEST: Verify prefix uses connector_instance_id, not connector_type.
        Per §3: This allows multiple instances of the same connector type per tenant.
        """
        # Two instances of the same connector type
        path_1 = storage_client.get_full_path(
            tenant_id="123",
            connector_instance_id="github_org1",
            object_path="repo.json"
        )
        
        path_2 = storage_client.get_full_path(
            tenant_id="123",
            connector_instance_id="github_org2",
            object_path="repo.json"
        )
        
        # Should be different paths
        assert path_1 == "tenant_123/connector_github_org1/repo.json"
        assert path_2 == "tenant_123/connector_github_org2/repo.json"
        assert path_1 != path_2
    
    def test_bucket_credentials_from_vault(self, storage_client):
        """
        CRITICAL TEST: Verify bucket credentials are retrieved from vault.
        Per spec: Bucket access keys go through the vault client, never inline in config.
        """
        # Verify credentials were retrieved during initialization
        assert storage_client._bucket_credentials is not None
        assert "access_key" in storage_client._bucket_credentials
        assert "secret_key" in storage_client._bucket_credentials
    
    def test_cross_tenant_isolation_in_paths(self, storage_client):
        """
        CRITICAL TEST: Verify paths are tenant-isolated by construction.
        Different tenants cannot accidentally access each other's objects.
        """
        path_tenant_a = storage_client.get_full_path(
            tenant_id="tenant_a",
            connector_instance_id="connector_1",
            object_path="file.txt"
        )
        
        path_tenant_b = storage_client.get_full_path(
            tenant_id="tenant_b",
            connector_instance_id="connector_1",
            object_path="file.txt"
        )
        
        # Paths should be different due to tenant prefix
        assert path_tenant_a != path_tenant_b
        assert "tenant_tenant_a" in path_tenant_a
        assert "tenant_tenant_b" in path_tenant_b
    
    def test_list_objects_with_prefix(self, storage_client, mock_storage):
        """Test listing objects with additional prefix filter"""
        # Upload objects with different prefixes
        storage_client.upload(
            tenant_id="123",
            connector_instance_id="github_1",
            object_path="docs/readme.md",
            data=b"readme"
        )
        storage_client.upload(
            tenant_id="123",
            connector_instance_id="github_1",
            object_path="docs/guide.md",
            data=b"guide"
        )
        storage_client.upload(
            tenant_id="123",
            connector_instance_id="github_1",
            object_path="images/logo.png",
            data=b"logo"
        )
        
        # List only docs prefix
        docs_objects = storage_client.list_objects(
            tenant_id="123",
            connector_instance_id="github_1",
            prefix="docs/"
        )
        
        assert set(docs_objects) == {"docs/readme.md", "docs/guide.md"}
        assert "images/logo.png" not in docs_objects


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
