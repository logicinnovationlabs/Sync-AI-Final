"""
Gmail API client - thin wrapper around google-api-python-client.

Provides methods for:
- messages.list (backfill)
- messages.get (fetch full message)
- history.list (incremental sync + deletion detection)
- users.watch (Pub/Sub push notifications)
"""

from typing import Dict, Any, List, Optional
import base64
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials


class GmailClient:
    """
    Thin wrapper around Gmail API v1.
    
    All methods accept a token string and build the service on-demand.
    """
    
    API_SERVICE_NAME = "gmail"
    API_VERSION = "v1"
    USER_ID = "me"  # Always use 'me' for the authenticated user
    
    def __init__(self):
        """Initialize Gmail client."""
        pass
    
    def _build_service(self, access_token: str):
        """
        Build Gmail service with access token.
        
        Args:
            access_token: Valid OAuth access token
            
        Returns:
            Gmail service instance
        """
        credentials = Credentials(
            token=access_token,
            refresh_token="mock_refresh_token",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="mock_client_id",
            client_secret="mock_client_secret",
        )
        return build(
            self.API_SERVICE_NAME,
            self.API_VERSION,
            credentials=credentials,
            cache_discovery=False,
        )
    
    async def list_messages(
        self,
        access_token: str,
        page_size: int = 100,
        page_token: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List messages (used for initial backfill).
        
        Args:
            access_token: Valid OAuth token
            page_size: Number of messages per page
            page_token: Pagination token
            query: Optional Gmail search query
            
        Returns:
            Response dict with 'messages' list and 'nextPageToken'
        """
        service = self._build_service(access_token)
        
        request_params = {
            "userId": self.USER_ID,
            "maxResults": page_size,
        }
        
        if page_token:
            request_params["pageToken"] = page_token
        
        if query:
            request_params["q"] = query
        
        try:
            response = service.users().messages().list(**request_params).execute()
            return response
        except HttpError as e:
            raise Exception(f"Gmail API error: {e}")
    
    async def get_message(
        self,
        access_token: str,
        message_id: str,
        format: str = "full",
    ) -> Dict[str, Any]:
        """
        Get a single message by ID.
        
        Args:
            access_token: Valid OAuth token
            message_id: Message identifier
            format: Message format ('full', 'metadata', 'minimal', 'raw')
            
        Returns:
            Message dict with headers, payload, etc.
        """
        service = self._build_service(access_token)
        
        try:
            response = service.users().messages().get(
                userId=self.USER_ID,
                id=message_id,
                format=format,
            ).execute()
            return response
        except HttpError as e:
            raise Exception(f"Gmail get message API error: {e}")
    
    async def list_history(
        self,
        access_token: str,
        start_history_id: str,
        page_token: Optional[str] = None,
        max_results: int = 100,
        history_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        List history records (incremental sync).
        
        Args:
            access_token: Valid OAuth token
            start_history_id: Starting history ID
            page_token: Pagination token
            max_results: Max number of history records
            history_types: Optional list of types ('messageAdded', 'messageDeleted', etc.)
            
        Returns:
            Response dict with 'history' list, 'historyId', 'nextPageToken'
        """
        service = self._build_service(access_token)
        
        request_params = {
            "userId": self.USER_ID,
            "startHistoryId": start_history_id,
            "maxResults": max_results,
        }
        
        if page_token:
            request_params["pageToken"] = page_token
        
        if history_types:
            request_params["historyTypes"] = history_types
        
        try:
            response = service.users().history().list(**request_params).execute()
            return response
        except HttpError as e:
            # If history ID is too old, Gmail returns 404
            if e.resp.status == 404:
                return {"history": [], "historyId": start_history_id}
            raise Exception(f"Gmail history API error: {e}")
    
    async def watch(
        self,
        access_token: str,
        topic_name: str,
        label_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Set up a Pub/Sub watch for push notifications.
        
        Args:
            access_token: Valid OAuth token
            topic_name: Full Pub/Sub topic name (projects/{project}/topics/{topic})
            label_ids: Optional list of label IDs to watch
            
        Returns:
            Watch response with historyId and expiration
        """
        service = self._build_service(access_token)
        
        body = {
            "topicName": topic_name,
        }
        
        if label_ids:
            body["labelIds"] = label_ids
        
        try:
            response = service.users().watch(
                userId=self.USER_ID,
                body=body,
            ).execute()
            return response
        except HttpError as e:
            raise Exception(f"Gmail watch API error: {e}")
    
    async def stop(self, access_token: str) -> None:
        """
        Stop the current watch.
        
        Args:
            access_token: Valid OAuth token
        """
        service = self._build_service(access_token)
        
        try:
            service.users().stop(userId=self.USER_ID).execute()
        except HttpError as e:
            # Silently ignore errors (watch may already be stopped)
            pass
    
    async def get_profile(self, access_token: str) -> Dict[str, Any]:
        """Return the authenticated user's Gmail profile (emailAddress, historyId)."""
        service = self._build_service(access_token)
        try:
            return service.users().getProfile(userId=self.USER_ID).execute()
        except HttpError as e:
            raise Exception(f"Gmail getProfile API error: {e}")

    def decode_message_body(self, payload: Dict[str, Any]) -> str:
        """
        Decode message body from Gmail API payload.
        
        Handles multipart messages and base64url decoding.
        
        Args:
            payload: Message payload from Gmail API
            
        Returns:
            Decoded plain text content
        """
        body = ""
        
        if "parts" in payload:
            # Multipart message
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                        break
                elif part.get("mimeType") == "text/html" and not body:
                    # Fallback to HTML if no plain text
                    data = part.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        else:
            # Simple message
            data = payload.get("body", {}).get("data", "")
            if data:
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        
        return body
    
    def extract_header(self, message: Dict[str, Any], header_name: str) -> str:
        """
        Extract a header value from a message.
        
        Args:
            message: Message dict from Gmail API
            header_name: Header name (case-insensitive)
            
        Returns:
            Header value or empty string
        """
        headers = message.get("payload", {}).get("headers", [])
        header_name_lower = header_name.lower()
        
        for header in headers:
            if header.get("name", "").lower() == header_name_lower:
                return header.get("value", "")
        
        return ""
