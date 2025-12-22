"""
Pydantic models for Pipeline Manager.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
import uuid


class PipelineMode(str, Enum):
    """Pipeline execution mode."""
    AUTO = "auto"
    STEP = "step"


class PipelineStatus(str, Enum):
    """Pipeline run status."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PhaseStatus(str, Enum):
    """Phase execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelinePhase(str, Enum):
    """Pipeline phases."""
    LEAD_GENERATION = "lead_generation"
    CURATION = "curation"
    STORY_RESEARCH = "story_research"
    TEXT_GENERATION = "text_generation"
    PHOTO_RESEARCH = "photo_research"
    THUMBNAIL_GENERATION = "thumbnail_generation"


# Phase configuration with order and display names
PHASE_CONFIG = {
    PipelinePhase.LEAD_GENERATION: {"order": 1, "name": "Lead Generation", "short": "Leads"},
    PipelinePhase.CURATION: {"order": 1, "name": "Curation", "short": "Curation"},  # Combined with lead gen in Phase 1
    PipelinePhase.STORY_RESEARCH: {"order": 2, "name": "Story Research", "short": "Research"},
    PipelinePhase.TEXT_GENERATION: {"order": 3, "name": "Text Generation", "short": "Text"},
    PipelinePhase.PHOTO_RESEARCH: {"order": 4, "name": "Photo Research", "short": "Photos"},
    PipelinePhase.THUMBNAIL_GENERATION: {"order": 5, "name": "Thumbnail Generation", "short": "Thumbs"},
}


# === Request Models ===

class StartPipelineRequest(BaseModel):
    """Request to start a new pipeline run."""
    mode: PipelineMode = PipelineMode.AUTO
    config: Dict[str, Any] = Field(default_factory=dict)


class CancelRunRequest(BaseModel):
    """Request to cancel a pipeline run."""
    delete_data: bool = True


# === Response Models ===

class PipelineStats(BaseModel):
    """Statistics for a pipeline run."""
    leads_discovered: int = 0
    leads_approved: int = 0
    research_completed: int = 0
    generations_completed: int = 0
    photos_found: int = 0
    photos_approved: int = 0
    thumbnails_generated: int = 0


class PhaseProgress(BaseModel):
    """Progress information for a phase."""
    phase: str
    status: PhaseStatus = PhaseStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_items: int = 0
    completed_items: int = 0
    error_message: Optional[str] = None


class PipelineRunSummary(BaseModel):
    """Summary of a pipeline run for list views."""
    id: str
    mode: PipelineMode
    status: PipelineStatus
    current_phase: Optional[str] = None
    current_phase_index: int = 0
    total_phases: int = 5
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    stats: PipelineStats = Field(default_factory=PipelineStats)
    config: Dict[str, Any] = Field(default_factory=dict)


class PipelineRunDetail(PipelineRunSummary):
    """Full details of a pipeline run."""
    phases: List[PhaseProgress] = Field(default_factory=list)
    error_message: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class StoryStatusInPipeline(BaseModel):
    """Status of a story within a pipeline run."""
    id: str
    lead_id: Optional[str] = None
    story_research_id: Optional[str] = None
    story_generation_id: Optional[str] = None
    title: str
    phase_statuses: Dict[str, Any] = Field(default_factory=dict)
    current_phase: Optional[str] = None
    current_status: str = "pending"


class LeadResult(BaseModel):
    """Lead generation result."""
    id: str
    title: str
    url: str
    summary: Optional[str] = None
    source_origin: Optional[str] = None
    virality_score: Optional[int] = None
    brand_score: Optional[int] = None
    viral_hook: Optional[str] = None
    domain_tag: Optional[str] = None
    curator_reasoning: Optional[str] = None


class ResearchResult(BaseModel):
    """Story research result."""
    id: str
    lead_id: str
    title: str
    status: str
    ground_truth: Optional[str] = None
    hook: Optional[str] = None
    primary_sources: List[str] = Field(default_factory=list)


class TextGenerationResult(BaseModel):
    """Text generation result."""
    id: str
    story_research_id: str
    title: str
    hook_title: str
    subtitle: str
    domain_tag: str
    slide_count: int
    character_count: int
    instagram_caption: Optional[str] = None
    hashtags: List[str] = Field(default_factory=list)
    cover_options: List[Dict[str, Any]] = Field(default_factory=list)


class PhotoResult(BaseModel):
    """Photo research result."""
    id: str
    story_research_id: str
    image_url: str
    status: str
    relevance_score: Optional[int] = None
    verifiability_score: Optional[int] = None
    description: Optional[str] = None
    source_page_url: Optional[str] = None


class ThumbnailResult(BaseModel):
    """Thumbnail generation result."""
    id: str
    story_generation_id: str
    concept_number: int
    concept_type: str
    scene_description: str
    image_url: Optional[str] = None
    status: str
    is_selected: bool = False


# === Phase Data Visualization Models ===

class ScoreDistribution(BaseModel):
    """Score distribution statistics."""
    min: int = 0
    max: int = 0
    mean: float = 0
    scores: List[int] = Field(default_factory=list)


class FunnelData(BaseModel):
    """Lead generation funnel data."""
    rss_scanned: int = 0
    perplexity_discovered: int = 0
    total_candidates: int = 0
    url_deduped: int = 0
    url_dupes_removed: int = 0
    gatekeeper_passed: int = 0
    gatekeeper_filtered: Dict[str, int] = Field(default_factory=dict)
    semantic_unique: int = 0
    semantic_dupes: int = 0
    viral_passed: int = 0
    viral_failed: int = 0
    brand_passed: int = 0
    brand_failed: int = 0
    curator_selected: int = 0
    curator_saved: int = 0


class Phase1Data(BaseModel):
    """Comprehensive Phase 1 (Lead Generation) data."""
    phase: str = "lead_generation"
    total_leads: int = 0
    approved_leads: int = 0
    funnel: FunnelData = Field(default_factory=FunnelData)
    score_distributions: Dict[str, ScoreDistribution] = Field(default_factory=dict)
    source_breakdown: Dict[str, int] = Field(default_factory=dict)
    leads: List[Dict[str, Any]] = Field(default_factory=list)


class ResearchHook(BaseModel):
    """Research hook/angle data."""
    question: Optional[str] = None
    answer: Optional[str] = None


class ResearchItem(BaseModel):
    """Individual research item."""
    id: str
    lead_id: str
    title: str
    url: Optional[str] = None
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    ground_truth: Optional[str] = None
    ground_truth_char_count: int = 0
    hook: Optional[ResearchHook] = None
    primary_sources: List[str] = Field(default_factory=list)
    primary_source_urls: List[str] = Field(default_factory=list)
    research_time_seconds: int = 0


class Phase2Data(BaseModel):
    """Comprehensive Phase 2 (Story Research) data."""
    phase: str = "story_research"
    summary: Dict[str, int] = Field(default_factory=dict)
    total_ground_truth_chars: int = 0
    average_research_time_seconds: int = 0
    research: List[ResearchItem] = Field(default_factory=list)


class SlideItem(BaseModel):
    """Individual slide data."""
    order: int
    tag: str
    paragraph_count: int = 1
    text: str
    char_count: int = 0


class CoverOption(BaseModel):
    """Cover option data."""
    option_id: int
    hook_title: str
    subtitle: str
    domain_tag: str


class CoverData(BaseModel):
    """Cover options data."""
    selected_option: int = 1
    options: List[CoverOption] = Field(default_factory=list)


class GenerationItem(BaseModel):
    """Individual generation item."""
    id: str
    story_research_id: str
    lead_title: str
    hook_title: str
    subtitle: str
    domain_tag: str
    cover: CoverData = Field(default_factory=CoverData)
    slides: List[SlideItem] = Field(default_factory=list)
    total_slides: int = 0
    total_characters: int = 0
    caption: Optional[str] = None
    caption_char_count: int = 0
    hashtags: List[str] = Field(default_factory=list)


class Phase3Data(BaseModel):
    """Comprehensive Phase 3 (Text Generation) data."""
    phase: str = "text_generation"
    summary: Dict[str, int] = Field(default_factory=dict)
    generations: List[GenerationItem] = Field(default_factory=list)


class PhotoScores(BaseModel):
    """Photo scoring data."""
    relevance: Optional[int] = None
    verifiability: Optional[int] = None
    usability: Optional[int] = None


class PhotoSource(BaseModel):
    """Photo source information."""
    page_url: Optional[str] = None
    attribution: Optional[str] = None


class PhotoAnalysis(BaseModel):
    """AI analysis of photo."""
    description: Optional[str] = None
    generated_caption: Optional[str] = None


class PhotoItem(BaseModel):
    """Individual photo item."""
    id: str
    image_url: str
    status: str
    scores: PhotoScores = Field(default_factory=PhotoScores)
    is_ai_generated: bool = False
    is_hero: bool = False
    placement: Optional[Dict[str, Any]] = None
    source: PhotoSource = Field(default_factory=PhotoSource)
    ai_analysis: PhotoAnalysis = Field(default_factory=PhotoAnalysis)
    search_query: Optional[str] = None
    concept_tag: Optional[str] = None


class PhotosByStory(BaseModel):
    """Photos grouped by story."""
    story_research_id: str
    story_title: str
    queries_used: List[str] = Field(default_factory=list)
    photos: List[PhotoItem] = Field(default_factory=list)
    approved_count: int = 0
    rejected_count: int = 0


class Phase4Data(BaseModel):
    """Comprehensive Phase 4 (Photo Research) data."""
    phase: str = "photo_research"
    summary: Dict[str, Any] = Field(default_factory=dict)
    score_averages: Dict[str, float] = Field(default_factory=dict)
    photos_by_story: List[PhotosByStory] = Field(default_factory=list)


class ThumbnailItem(BaseModel):
    """Individual thumbnail item."""
    id: str
    concept_number: int
    concept_type: str
    is_selected: bool = False
    status: str
    scene_description: Optional[str] = None
    full_prompt: Optional[str] = None
    image_url: Optional[str] = None
    generation_metadata: Dict[str, Any] = Field(default_factory=dict)


class ThumbnailsByStory(BaseModel):
    """Thumbnails grouped by story."""
    story_generation_id: str
    hook_title: str
    subtitle: str
    domain_tag: str
    thumbnails: List[ThumbnailItem] = Field(default_factory=list)


class Phase5Data(BaseModel):
    """Comprehensive Phase 5 (Thumbnail Generation) data."""
    phase: str = "thumbnail_generation"
    summary: Dict[str, Any] = Field(default_factory=dict)
    concept_type_breakdown: Dict[str, int] = Field(default_factory=dict)
    thumbnails_by_story: List[ThumbnailsByStory] = Field(default_factory=list)


class CleanupPreview(BaseModel):
    """Preview of data that would be deleted on cancellation."""
    leads: int = 0
    research: int = 0
    generations: int = 0
    slides: int = 0
    photos: int = 0
    thumbnails: int = 0


class ActiveRunResponse(BaseModel):
    """Response for checking active run."""
    has_active_run: bool
    run: Optional[PipelineRunSummary] = None
    redirect_url: Optional[str] = None


# === SSE Event Models ===

class SSEEvent(BaseModel):
    """Server-Sent Event model."""
    event: str
    data: Dict[str, Any]


class ProgressEvent(BaseModel):
    """Progress update event."""
    run_id: str
    status: str
    current_phase: Optional[str] = None
    current_phase_index: int = 0
    stats: PipelineStats = Field(default_factory=PipelineStats)
    phases: List[PhaseProgress] = Field(default_factory=list)


class StoryUpdateEvent(BaseModel):
    """Story status update event."""
    run_id: str
    story_id: str
    phase: str
    status: str
    message: Optional[str] = None

