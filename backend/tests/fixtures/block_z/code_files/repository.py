"""Repository pattern for data access."""
from typing import List, Optional, Any

class UserRepository:
    """Repository for User data access."""
    
    def __init__(self, db):
        self.db = db
    
    def find_all(self) -> List[Any]:
        """Retrieve all users."""
        return self.db.query("SELECT * FROM users")
    
    def find_by_id(self, user_id: str) -> Optional[Any]:
        """Find a user by ID."""
        result = self.db.query_one("SELECT * FROM users WHERE id = %s", (user_id,))
        return result if result else None
    
    def find_by_email(self, email: str) -> Optional[Any]:
        """Find a user by email."""
        result = self.db.query_one("SELECT * FROM users WHERE email = %s", (email,))
        return result if result else None
    
    def create(self, user_data: dict) -> Any:
        """Create a new user."""
        query = """
            INSERT INTO users (email, first_name, last_name, role)
            VALUES (%s, %s, %s, %s)
            RETURNING *
        """
        return self.db.query_one(query, (
            user_data['email'],
            user_data['first_name'],
            user_data['last_name'],
            user_data.get('role', 'user')
        ))
    
    def update(self, user_id: str, user_data: dict) -> Optional[Any]:
        """Update a user."""
        query = """
            UPDATE users
            SET email = %s, first_name = %s, last_name = %s, role = %s
            WHERE id = %s
            RETURNING *
        """
        return self.db.query_one(query, (
            user_data['email'],
            user_data['first_name'],
            user_data['last_name'],
            user_data['role'],
            user_id
        ))
    
    def delete(self, user_id: str) -> bool:
        """Delete a user."""
        result = self.db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        return result > 0

class DocumentRepository:
    """Repository for Document data access."""
    
    def __init__(self, db):
        self.db = db
    
    def find_all(self, limit: int = 100, offset: int = 0) -> List[Any]:
        """Retrieve all documents with pagination."""
        return self.db.query(
            "SELECT * FROM documents LIMIT %s OFFSET %s",
            (limit, offset)
        )
    
    def find_by_id(self, doc_id: str) -> Optional[Any]:
        """Find a document by ID."""
        result = self.db.query_one("SELECT * FROM documents WHERE id = %s", (doc_id,))
        return result if result else None
    
    def search(self, query: str, limit: int = 20) -> List[Any]:
        """Search documents by query."""
        return self.db.query(
            "SELECT * FROM documents WHERE title ILIKE %s OR body ILIKE %s LIMIT %s",
            (f"%{query}%", f"%{query}%", limit)
        )
    
    def create(self, doc_data: dict) -> Any:
        """Create a new document."""
        query = """
            INSERT INTO documents (title, body, author, tags, visibility)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
        """
        return self.db.query_one(query, (
            doc_data['title'],
            doc_data['body'],
            doc_data['author'],
            doc_data.get('tags', []),
            doc_data.get('visibility', 'public')
        ))
    
    def delete(self, doc_id: str) -> bool:
        """Delete a document."""
        result = self.db.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
        return result > 0
