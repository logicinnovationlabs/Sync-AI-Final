"""Service layer for business logic."""
from typing import List, Optional, Any

class EmailService:
    """Service for sending emails."""
    
    def __init__(self, smtp_config: dict):
        self.smtp_config = smtp_config
    
    def send_email(self, to: str, subject: str, body: str) -> bool:
        """Send an email."""
        print(f"Sending email to {to}: {subject}")
        # Actual email sending logic would go here
        return True
    
    def send_welcome_email(self, user: Any) -> bool:
        """Send a welcome email to a new user."""
        subject = "Welcome to our platform!"
        body = f"Hello {user.first_name}, welcome to our platform!"
        return self.send_email(user.email, subject, body)
    
    def send_password_reset(self, user: Any, reset_token: str) -> bool:
        """Send a password reset email."""
        subject = "Password Reset Request"
        body = f"Click here to reset your password: /reset/{reset_token}"
        return self.send_email(user.email, subject, body)

class SearchService:
    """Service for search operations."""
    
    def __init__(self, search_client):
        self.client = search_client
    
    def search_documents(self, query: str, filters: dict = None, page: int = 1, page_size: int = 20) -> dict:
        """Search for documents."""
        # Build search query
        search_params = {
            "query": query,
            "from": (page - 1) * page_size,
            "size": page_size
        }
        
        if filters:
            search_params["filters"] = filters
        
        # Execute search
        results = self.client.search(**search_params)
        
        return {
            "total": results["total"],
            "page": page,
            "page_size": page_size,
            "results": results["hits"]
        }
    
    def index_document(self, document: Any) -> bool:
        """Index a document for search."""
        return self.client.index(document.id, document.to_dict())
    
    def delete_document(self, doc_id: str) -> bool:
        """Remove a document from the search index."""
        return self.client.delete(doc_id)

class UserService:
    """Service for user operations."""
    
    def __init__(self, user_repository, email_service):
        self.repository = user_repository
        self.email_service = email_service
    
    def create_user(self, user_data: dict) -> Any:
        """Create a new user."""
        # Create user in database
        user = self.repository.create(user_data)
        
        # Send welcome email
        self.email_service.send_welcome_email(user)
        
        return user
    
    def get_user(self, user_id: str) -> Optional[Any]:
        """Get a user by ID."""
        return self.repository.find_by_id(user_id)
    
    def update_user(self, user_id: str, user_data: dict) -> Optional[Any]:
        """Update a user."""
        return self.repository.update(user_id, user_data)
    
    def delete_user(self, user_id: str) -> bool:
        """Delete a user."""
        return self.repository.delete(user_id)
