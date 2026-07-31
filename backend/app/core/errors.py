"""
Shared error envelope schema for all 4xx/5xx responses.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Error detail structure."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    field: Optional[str] = Field(None, description="Field that caused the error (if applicable)")
    meta: Optional[Dict[str, Any]] = Field(
        None, description="Additional context about the error"
    )


class ErrorResponse(BaseModel):
    """Standard error envelope for all API errors."""

    error: ErrorDetail = Field(..., description="Error details")
    request_id: Optional[str] = Field(None, description="Request ID for tracing")
    timestamp: str = Field(..., description="ISO 8601 timestamp of the error")

    class Config:
        json_schema_extra = {
            "example": {
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Missing required scope: search.read",
                    "field": None,
                    "meta": {"required_scope": "search.read"},
                },
                "request_id": "req_abc123",
                "timestamp": "2026-07-30T10:39:00Z",
            }
        }
