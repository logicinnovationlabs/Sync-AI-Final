"""Test utilities and fixtures."""
import pytest
from typing import Generator, Any

@pytest.fixture
def mock_database():
    """Mock database fixture."""
    class MockDB:
        def __init__(self):
            self.data = {}
        
        def query(self, sql: str, params: tuple = None):
            return []
        
        def query_one(self, sql: str, params: tuple = None):
            return None
        
        def execute(self, sql: str, params: tuple = None):
            return 1
    
    return MockDB()

@pytest.fixture
def mock_user():
    """Mock user fixture."""
    class MockUser:
        id = "user123"
        email = "test@example.com"
        first_name = "John"
        last_name = "Doe"
        role = "user"
        created_at = "2026-01-01T00:00:00Z"
        updated_at = "2026-01-01T00:00:00Z"
    
    return MockUser()

@pytest.fixture
def mock_document():
    """Mock document fixture."""
    class MockDocument:
        id = "doc123"
        title = "Test Document"
        body = "This is a test document body"
        author = "user123"
        tags = ["test", "example"]
        visibility = "public"
        created_at = "2026-01-01T00:00:00Z"
        
        def to_dict(self):
            return {
                "id": self.id,
                "title": self.title,
                "body": self.body,
                "author": self.author,
                "tags": self.tags
            }
    
    return MockDocument()

def create_test_user(email: str = "test@example.com", role: str = "user") -> dict:
    """Create a test user dictionary."""
    return {
        "email": email,
        "first_name": "Test",
        "last_name": "User",
        "role": role
    }

def create_test_document(title: str = "Test Doc", author: str = "user123") -> dict:
    """Create a test document dictionary."""
    return {
        "title": title,
        "body": "Test document body",
        "author": author,
        "tags": ["test"],
        "visibility": "public"
    }

class TestHelper:
    """Helper class for tests."""
    
    @staticmethod
    def assert_valid_email(email: str):
        """Assert that an email is valid."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        assert re.match(pattern, email), f"Invalid email: {email}"
    
    @staticmethod
    def assert_valid_id(id_str: str):
        """Assert that an ID is valid."""
        assert id_str and len(id_str) > 0, "ID cannot be empty"
