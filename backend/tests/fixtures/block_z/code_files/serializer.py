"""Serializers for API models."""
from typing import Dict, Any, List

class UserSerializer:
    """Serializer for User model."""
    
    @staticmethod
    def serialize(user: Any) -> Dict[str, Any]:
        """Serialize a user object to a dictionary."""
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "created_at": user.created_at.isoformat() if hasattr(user.created_at, 'isoformat') else str(user.created_at),
            "updated_at": user.updated_at.isoformat() if hasattr(user.updated_at, 'isoformat') else str(user.updated_at)
        }
    
    @staticmethod
    def serialize_many(users: List[Any]) -> List[Dict[str, Any]]:
        """Serialize multiple user objects."""
        return [UserSerializer.serialize(user) for user in users]

class DocumentSerializer:
    """Serializer for Document model."""
    
    @staticmethod
    def serialize(document: Any) -> Dict[str, Any]:
        """Serialize a document object to a dictionary."""
        return {
            "id": document.id,
            "title": document.title,
            "body": document.body,
            "author": document.author,
            "tags": document.tags,
            "visibility": document.visibility,
            "created_at": document.created_at.isoformat() if hasattr(document.created_at, 'isoformat') else str(document.created_at)
        }
    
    @staticmethod
    def serialize_many(documents: List[Any]) -> List[Dict[str, Any]]:
        """Serialize multiple document objects."""
        return [DocumentSerializer.serialize(doc) for doc in documents]

class SearchResultSerializer:
    """Serializer for search results."""
    
    @staticmethod
    def serialize(results: Any) -> Dict[str, Any]:
        """Serialize search results."""
        return {
            "total": results.total,
            "page": results.page,
            "page_size": results.page_size,
            "results": DocumentSerializer.serialize_many(results.documents)
        }
