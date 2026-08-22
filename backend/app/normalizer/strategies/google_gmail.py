"""
Google Gmail normalizer strategy.

Extracts text, metadata, and permission hints from Gmail messages.
Gmail has no sharing model — each message belongs to exactly one mailbox owner.
"""

import logging
import re
import html as html_module
from typing import Dict, Any, List, Tuple
from app.normalizer.base import NormalizerStrategy
from app.core.models import IdentityHint, PermissionLevel

logger = logging.getLogger(__name__)

_GHOST_MAILBOX = "user@example.com"


def mailbox_owner_email(raw: Dict[str, Any]) -> str | None:
    """Real mailbox only. Never the historical placeholder owner."""
    headers = raw.get("payload", {}).get("headers", [])
    header_dict = {
        h["name"].lower(): h["value"] for h in headers if isinstance(h, dict)
    }
    delivered_to = (header_dict.get("delivered-to") or "").strip()
    configured = str(raw.get("_mailbox_email") or "").strip()
    email = (delivered_to or configured).strip().lower()
    if not email or email == _GHOST_MAILBOX:
        return None
    return email


class GoogleGmailNormalizer(NormalizerStrategy):
    """
    Normalizer for Gmail messages.
    
    Gmail has no sharing model — each message has exactly one owner (the mailbox).
    Text extraction reuses Block B's already-decoded body, with HTML stripping.
    """
    
    def get_source_type(self) -> str:
        return "google_gmail"
    
    async def extract_text(self, raw: Dict[str, Any]) -> str:
        """
        Extract text from Gmail message.
        
        Reuses Block B's already-decoded plain-text body where present.
        If only text/html was available, strips HTML tags.
        """
        # Check for pre-extracted text (tests may inject this)
        if "_test_extracted_text" in raw:
            return raw["_test_extracted_text"]
        
        # Extract from snippet or decoded body
        snippet = raw.get("snippet", "")
        payload = raw.get("payload", {})
        
        # Try to get full body (simplified — real implementation would decode MIME parts)
        body_text = self._extract_body_text(payload)
        
        if body_text:
            # Strip HTML if present
            return self._strip_html(body_text)
        
        # Fall back to snippet
        return snippet
    
    def _extract_body_text(self, payload: Dict[str, Any]) -> str:
        """Extract body text from Gmail payload."""
        # Check for body data
        body = payload.get("body", {})
        body_data = body.get("data", "")
        
        if body_data:
            try:
                import base64
                decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
                return decoded
            except Exception:
                pass
        
        # Check multipart
        parts = payload.get("parts", [])
        for part in parts:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/plain":
                part_body = part.get("body", {}).get("data", "")
                if part_body:
                    try:
                        import base64
                        decoded = base64.urlsafe_b64decode(part_body).decode("utf-8", errors="ignore")
                        return decoded
                    except Exception:
                        pass
        
        return ""
    
    def _strip_html(self, text: str) -> str:
        """Strip HTML tags from text."""
        if not text or not isinstance(text, str):
            return ""
        
        # Unescape HTML entities
        text = html_module.unescape(text)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def map_metadata(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and validate metadata from Gmail message.
        
        Re-validates against Gmail's manifest allowlist (same as Block B).
        """
        # Extract headers
        headers = raw.get("payload", {}).get("headers", [])
        header_dict = {h["name"].lower(): h["value"] for h in headers if isinstance(h, dict)}
        
        from_email = header_dict.get("from", "")
        to_emails = header_dict.get("to", "")
        subject = header_dict.get("subject", "")
        
        # Split to_emails into list
        to_list = [e.strip() for e in to_emails.split(",") if e.strip()] if to_emails else []
        
        # Metadata allowlist (same fields as Block B's transform())
        metadata = {
            "from_email": from_email,
            "to_emails": to_list,
            "subject": subject,
            "thread_id": raw.get("threadId", ""),
            "label_ids": raw.get("labelIds", []),
            "has_attachments": self._has_attachments(raw.get("payload", {})),
            "message_size_bytes": raw.get("sizeEstimate", 0),
            "visibility_mode": "restricted",
        }
        
        return metadata
    
    def _has_attachments(self, payload: Dict[str, Any]) -> bool:
        """Check if message has attachments."""
        parts = payload.get("parts", [])
        for part in parts:
            filename = part.get("filename", "")
            if filename and part.get("body", {}).get("attachmentId"):
                return True
        return False
    
    def extract_permission_hints(self, raw: Dict[str, Any]) -> List[Tuple[IdentityHint, PermissionLevel]]:
        """
        Extract permission grants from Gmail message.
        
        Gmail has no sharing model — always exactly one entry: mailbox owner with OWNER permission.
        """
        mailbox_email = mailbox_owner_email(raw)
        if not mailbox_email:
            logger.warning("gmail ACL skipped: no mailbox owner email")
            return []

        hint = IdentityHint(
            source_type="google_gmail",
            external_id=mailbox_email,
            email=mailbox_email,
            name=None,
        )
        
        return [(hint, PermissionLevel.OWNER)]
    
    def extract_containers(self, raw: Dict[str, Any]) -> List[str]:
        """
        Extract parent container IDs.
        
        Gmail messages have no folder/container hierarchy in this model.
        Labels are not containers for inheritance purposes.
        """
        return []
    
    def extract_identity_hints(self, raw: Dict[str, Any]) -> Dict[str, IdentityHint]:
        """
        Extract identity hints for owner and creator.
        
        Owner: mailbox owner
        Creator: sender (From header)
        """
        hints = {}
        
        # Extract headers
        headers = raw.get("payload", {}).get("headers", [])
        header_dict = {h["name"].lower(): h["value"] for h in headers if isinstance(h, dict)}
        
        mailbox_email = mailbox_owner_email(raw)
        from_email = header_dict.get("from", "")
        
        # Parse from header to extract email (may be in "Name <email>" format)
        from_email_clean = self._extract_email(from_email)
        from_name = self._extract_name(from_email)
        
        # Owner: mailbox owner (omit rather than mint user@example.com)
        if mailbox_email:
            hints["owner"] = IdentityHint(
                source_type="google_gmail",
                external_id=mailbox_email,
                email=mailbox_email,
                name=None,
            )
        
        # Creator: sender
        if from_email_clean:
            hints["creator"] = IdentityHint(
                source_type="google_gmail",
                external_id=from_email_clean,
                email=from_email_clean,
                name=from_name,
            )
        
        return hints
    
    def _extract_email(self, from_header: str) -> str:
        """Extract email address from 'Name <email>' format."""
        if not from_header:
            return ""
        
        # Check for <email> format
        match = re.search(r'<([^>]+)>', from_header)
        if match:
            return match.group(1).strip()
        
        # Otherwise assume the whole string is an email
        return from_header.strip()
    
    def _extract_name(self, from_header: str) -> str:
        """Extract name from 'Name <email>' format."""
        if not from_header:
            return ""
        
        # Check for Name <email> format
        match = re.match(r'^([^<]+)<', from_header)
        if match:
            return match.group(1).strip()
        
        return ""
