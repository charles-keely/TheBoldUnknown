"""
Pydantic models for the Scheduler API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class ScheduleStatus(str, Enum):
    SCHEDULED = "scheduled"      # Added to schedule, awaiting approval
    APPROVED = "approved"        # Approved for auto-posting
    PUBLISHING = "publishing"    # Currently being published
    PUBLISHED = "published"      # Successfully published
    FAILED = "failed"            # Failed after max retries


# =============================================================================
# Scheduled Post Models
# =============================================================================

class ScheduledPostSummary(BaseModel):
    """A scheduled post for the schedule view."""
    id: str
    story_generation_id: str
    assembly_id: Optional[str] = None
    
    # Story info for display
    hook_title: str
    subtitle: Optional[str] = None
    domain_tag: Optional[str] = None
    thumbnail_url: Optional[str] = None
    
    # Scheduling
    scheduled_at: datetime
    position: int
    
    # Status
    status: ScheduleStatus
    approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    instagram_media_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    
    # Metadata
    created_at: datetime
    updated_at: datetime


class ScheduleResponse(BaseModel):
    """Response for GET /api/schedule."""
    posts: List[ScheduledPostSummary]
    count: int
    pending_count: int      # scheduled status
    approved_count: int     # approved status  
    published_count: int    # published status
    failed_count: int       # failed status


class SyncScheduleResponse(BaseModel):
    """Response for POST /api/schedule/sync."""
    added: int
    already_scheduled: int
    schedule: List[ScheduledPostSummary]


class UpdateScheduledPostRequest(BaseModel):
    """Request body for PATCH /api/schedule/{post_id}."""
    scheduled_at: Optional[datetime] = None
    position: Optional[int] = None


class MovePostRequest(BaseModel):
    """Request body for POST /api/schedule/{post_id}/move."""
    new_position: int


class MovePostResponse(BaseModel):
    """Response for POST /api/schedule/{post_id}/move."""
    schedule: List[ScheduledPostSummary]


class ApproveScheduleResponse(BaseModel):
    """Response for POST /api/schedule/approve."""
    approved_count: int
    approval_id: str


class DeletePostResponse(BaseModel):
    """Response for DELETE /api/schedule/{post_id}."""
    success: bool
    message: str


# =============================================================================
# Token Models
# =============================================================================

class TokenStatus(BaseModel):
    """Token health status."""
    has_token: bool
    expires_at: Optional[datetime] = None
    days_until_expiry: Optional[float] = None
    is_healthy: bool
    needs_refresh: bool
    last_used_at: Optional[datetime] = None


class RefreshTokenResponse(BaseModel):
    """Response for POST /api/tokens/refresh."""
    success: bool
    message: str
    new_expires_at: Optional[datetime] = None


# =============================================================================
# Post Preview Models
# =============================================================================

class SlidePreview(BaseModel):
    """Preview data for a single slide."""
    index: int
    type: str
    template: str
    visible: bool
    thumbnail_url: Optional[str] = None  # For cover/photo slides
    text_preview: Optional[str] = None   # First 100 chars for text slides


class PostPreviewResponse(BaseModel):
    """Response for GET /api/schedule/{post_id}/preview."""
    story_generation_id: str
    hook_title: str
    subtitle: Optional[str] = None
    caption: Optional[str] = None
    hashtags: List[str] = []
    slide_count: int
    slides: List[SlidePreview]

