"""
Pydantic models for the Pre-Assembler API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class AssemblyStatus(str, Enum):
    NEW = "new"
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    FINALIZED = "finalized"


class SlideType(str, Enum):
    COVER = "cover"
    TEXT = "text"
    PHOTO = "photo"


class TemplateType(str, Enum):
    COVER3 = "cover3"
    EDITORIAL3 = "editorial3"
    PHOTOS1 = "photos1"
    CLOSING1 = "closing1"


# =============================================================================
# Story Models (for Dashboard)
# =============================================================================

class StorySummary(BaseModel):
    """Summary of a story for the dashboard."""
    story_generation_id: str
    story_research_id: str
    hook_title: str
    subtitle: str
    domain_tag: str
    # When false, this story should not be scheduled/published.
    is_enabled: bool = True
    # When true, this story has been approved to proceed to assembly workflow.
    approved_for_assembly: bool = False
    instagram_caption: Optional[str] = None
    hashtags: Optional[List[str]] = None
    slide_count: int
    photo_count: int
    thumbnail_url: Optional[str] = None
    thumbnail_count: int
    assembly_status: AssemblyStatus = AssemblyStatus.NEW
    created_at: datetime
    updated_at: Optional[datetime] = None


class StoriesResponse(BaseModel):
    """Response for GET /api/stories."""
    stories: List[StorySummary]
    count: int


# =============================================================================
# Story Full Data Models (for Editor)
# =============================================================================

class StoryGeneration(BaseModel):
    """A story generation (title/subtitle variation)."""
    id: str
    hook_title: str
    subtitle: str
    domain_tag: str


class UpdateStoryGenerationRequest(BaseModel):
    """Patch a story generation's title/subtitle fields and publish eligibility."""
    hook_title: Optional[str] = None
    subtitle: Optional[str] = None
    domain_tag: Optional[str] = None
    is_enabled: Optional[bool] = None
    approved_for_assembly: Optional[bool] = None


class StorySlide(BaseModel):
    """A text slide from story_slides."""
    id: str
    slide_order: int
    text_content: str
    document_type_tag: str
    paragraph_count: Optional[int] = None


class StoryPhoto(BaseModel):
    """An approved photo."""
    id: str
    image_url: str
    caption: Optional[str] = None
    source_attribution: Optional[str] = None
    concept_tag: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class StoryThumbnail(BaseModel):
    """A generated thumbnail."""
    id: str
    concept_number: int
    concept_type: str
    image_url: Optional[str] = None
    is_selected: bool = False
    status: str


class StoryInfo(BaseModel):
    """Core story info."""
    story_generation_id: str
    story_research_id: str
    hook_title: str
    subtitle: str
    domain_tag: str
    # When false, this story should not be scheduled/published.
    is_enabled: bool = True
    # When true, this story has been approved to proceed to assembly workflow.
    approved_for_assembly: bool = False
    instagram_caption: Optional[str] = None
    hashtags: Optional[List[str]] = None
    created_at: datetime
    lead_title: str
    research_data: Optional[Any] = None


class StoryFullData(BaseModel):
    """Complete story data for the editor."""
    story: StoryInfo
    generations: List[StoryGeneration]
    slides: List[StorySlide]
    photos: List[StoryPhoto]
    thumbnails: List[StoryThumbnail]


# =============================================================================
# Assembly Models
# =============================================================================

class SlideContent(BaseModel):
    """Content for a slide in the assembly."""
    # Cover content
    title: Optional[str] = None
    subtitle: Optional[str] = None
    thumbnail_url: Optional[str] = None
    # Non-destructive cover "crop" controls (applied via CSS transform)
    thumbnail_zoom: Optional[float] = None
    thumbnail_offset_x: Optional[float] = None
    thumbnail_offset_y: Optional[float] = None
    
    # Text content
    text: Optional[str] = None
    paragraph_count: Optional[int] = None
    
    # Photo content
    image_url: Optional[str] = None
    caption: Optional[str] = None
    source: Optional[str] = None

    # Closing slide content
    primary_sources: Optional[List[str]] = None
    primary_source_urls: Optional[List[str]] = None
    
    # Common
    domain_tag: Optional[str] = None


class AssemblySlide(BaseModel):
    """A slide in the assembly."""
    id: str
    type: SlideType
    template: TemplateType
    visible: bool = True
    content: SlideContent
    source_slide_id: Optional[str] = None
    source_photo_id: Optional[str] = None


class AssemblyMetadata(BaseModel):
    """Metadata for an assembly."""
    created_at: datetime
    updated_at: datetime
    last_edited_by: Optional[str] = None
    # When true, slide content has been hydrated from canonical story tables
    # (story_slides / story_photos / story_thumbnails) at least once.
    hydrated_from_story: Optional[bool] = None
    hydrated_at: Optional[datetime] = None


class AssemblyData(BaseModel):
    """The assembly configuration stored in JSONB."""
    version: int = 1
    story_generation_id: str
    # Which title/subtitle option (story_generations row) is currently selected for cover.
    selected_generation_id: Optional[str] = None
    # Per-option title/subtitle/domain_tag overrides keyed by the option id (e.g. "1".."6").
    # Shape: { "2": { "title": "...", "subtitle": "...", "domain_tag": "..." }, ... }
    title_overrides: Optional[Dict[str, Dict[str, str]]] = None
    selected_thumbnail_id: Optional[str] = None
    slides: List[AssemblySlide]
    metadata: Optional[AssemblyMetadata] = None


class Assembly(BaseModel):
    """Full assembly record from database."""
    id: str
    story_generation_id: str
    assembly_data: AssemblyData
    status: AssemblyStatus
    created_at: datetime
    updated_at: datetime


class AssemblyResponse(BaseModel):
    """Response for GET /api/stories/{id}/assembly."""
    assembly: Assembly
    is_default: bool = False


class SaveAssemblyRequest(BaseModel):
    """Request body for POST /api/stories/{id}/assembly."""
    assembly_data: AssemblyData
    status: AssemblyStatus = AssemblyStatus.DRAFT


class SaveAssemblyResponse(BaseModel):
    """Response for POST /api/stories/{id}/assembly."""
    id: str
    status: AssemblyStatus
    updated_at: datetime

