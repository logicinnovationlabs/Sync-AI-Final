"""Controller layer for handling HTTP requests."""
from typing import Any

class UserController:
    """Controller for user-related endpoints."""
    
    def __init__(self, user_service):
        self.service = user_service
    
    def get_user(self, user_id: str) -> dict:
        """Handle GET /users/:id request."""
        user = self.service.get_user(user_id)
        if not user:
            return {"error": "User not found"}, 404
        
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name
        }, 200
    
    def list_users(self, page: int = 1, page_size: int = 20) -> dict:
        """Handle GET /users request."""
        users = self.service.list_users(page, page_size)
        return {
            "users": [self._serialize_user(u) for u in users],
            "page": page,
            "page_size": page_size
        }, 200
    
    def create_user(self, user_data: dict) -> dict:
        """Handle POST /users request."""
        try:
            user = self.service.create_user(user_data)
            return self._serialize_user(user), 201
        except Exception as e:
            return {"error": str(e)}, 400
    
    def update_user(self, user_id: str, user_data: dict) -> dict:
        """Handle PUT /users/:id request."""
        try:
            user = self.service.update_user(user_id, user_data)
            if not user:
                return {"error": "User not found"}, 404
            return self._serialize_user(user), 200
        except Exception as e:
            return {"error": str(e)}, 400
    
    def delete_user(self, user_id: str) -> tuple:
        """Handle DELETE /users/:id request."""
        success = self.service.delete_user(user_id)
        if not success:
            return {"error": "User not found"}, 404
        return {}, 204
    
    def _serialize_user(self, user: Any) -> dict:
        """Serialize user object."""
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role
        }

class SearchController:
    """Controller for search-related endpoints."""
    
    def __init__(self, search_service):
        self.service = search_service
    
    def search(self, query: str, filters: dict = None, page: int = 1, page_size: int = 20) -> dict:
        """Handle GET /search request."""
        if not query:
            return {"error": "Query parameter is required"}, 400
        
        results = self.service.search_documents(query, filters, page, page_size)
        return results, 200
