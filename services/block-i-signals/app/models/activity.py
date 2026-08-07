"""Activity event and signal response models (canonical §7.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


EventType = Literal[
    "view",
    "edit",
    "authored",
    "commented_on",
    "referenced",
    "worked_on",
]
PrivacyLevel = Literal["public", "restricted", "confidential"]


class ActivityEvent(BaseModel):
    """Canonical activity event schema."""

    event_id: str
    tenant_id: Optional[str] = None  # ignored from body; taken from JWT
    actor_principal_id: str
    object_id: str
    event_type: EventType
    source_system: str
    event_time: datetime
    session_id: Optional[str] = None
    context_json: Optional[Dict[str, Any]] = None
    privacy_level: PrivacyLevel = "public"
    # Test/override TTL (seconds). When set, retention uses this instead of defaults.
    ttl_seconds: Optional[int] = None


class IngestRequest(BaseModel):
    events: List[ActivityEvent] = Field(default_factory=list)


class FailedEvent(BaseModel):
    event_id: str
    reason: str


class IngestResponse(BaseModel):
    status: str = "accepted"
    ingested_count: int = 0
    already_processed_count: int = 0
    failed_events: List[FailedEvent] = Field(default_factory=list)


class UserSignals(BaseModel):
    last_active: Optional[datetime] = None
    top_viewed_docs: List[str] = Field(default_factory=list)
    top_edited_docs: List[str] = Field(default_factory=list)
    authored_docs: List[str] = Field(default_factory=list)
    frequent_collaborators: List[str] = Field(default_factory=list)
    preferred_sources: List[str] = Field(default_factory=list)
    activity_heatmap: Dict[str, int] = Field(default_factory=dict)
    event_counts_by_type: Dict[str, int] = Field(default_factory=dict)


class UserSignalResponse(BaseModel):
    user_id: str
    tenant_id: str
    signals: UserSignals
    updated_at: datetime
    freshness_s: Optional[float] = None


class DocumentSignalResponse(BaseModel):
    document_id: str
    tenant_id: str
    privacy_protected: bool = False
    popularity_score: Optional[float] = None
    total_views: Optional[int] = None
    distinct_viewers: Optional[int] = None
    last_viewed: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    window_days: Optional[int] = None


class ActivityConfig(BaseModel):
    tenant_id: str
    privacy_threshold: int = 5
    retention_days: int = 90
    high_privacy_retention_days: int = 30
    enable_per_source_disablement: bool = False
    disabled_sources: List[str] = Field(default_factory=list)


class StoredEvent(BaseModel):
    event_id: str
    tenant_id: str
    actor_principal_id: str
    object_id: str
    event_type: str
    source_system: str
    event_time: datetime
    session_id: Optional[str] = None
    context_json: Optional[Dict[str, Any]] = None
    privacy_level: str = "public"
    ttl_seconds: int
    ingested_at: datetime


class PurgeResult(BaseModel):
    purged_events: int = 0
    tenants_touched: List[str] = Field(default_factory=list)
    aggregates_rebuilt: int = 0
