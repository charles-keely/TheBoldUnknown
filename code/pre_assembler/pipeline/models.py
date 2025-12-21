"""
Pipeline Models

Pydantic models for the unified content pipeline.
"""

from enum import Enum
from typing import Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field


class PipelinePhase(str, Enum):
    """Pipeline phases in order of execution."""
    LEAD_GENERATION = "lead_generation"
    CURATION = "curation"
    STORY_RESEARCH = "story_research"
    TEXT_GENERATION = "text_generation"
    PHOTO_RESEARCH = "photo_research"
    THUMBNAIL_GENERATION = "thumbnail_generation"


class PhaseStatus(str, Enum):
    """Status of a pipeline phase."""
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineMode(str, Enum):
    """Pipeline execution mode."""
    AUTOMATIC = "automatic"  # Runs all phases automatically
    STEP_BY_STEP = "step_by_step"  # Pauses after each phase for confirmation


class PhaseResult(BaseModel):
    """Result of a single phase execution."""
    phase: PipelinePhase
    status: PhaseStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    items_processed: int = 0
    items_created: int = 0
    items_failed: int = 0
    error_message: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)


class PipelineState(BaseModel):
    """Current state of the pipeline."""
    id: str
    mode: PipelineMode
    current_phase: Optional[PipelinePhase] = None
    is_running: bool = False
    is_paused: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    phases: dict[PipelinePhase, PhaseResult] = Field(default_factory=dict)
    error_message: Optional[str] = None
    
    # Summary stats
    total_leads_generated: int = 0
    total_stories_curated: int = 0
    total_stories_researched: int = 0
    total_stories_with_text: int = 0
    total_stories_with_photos: int = 0
    total_stories_with_thumbnails: int = 0
    
    class Config:
        use_enum_values = True


class PipelineConfig(BaseModel):
    """Configuration for a pipeline run."""
    mode: PipelineMode = PipelineMode.AUTOMATIC
    
    # Lead generation options
    lead_source: str = "all"  # "rss", "perplexity", or "all"
    
    # Curation options
    curation_dry_run: bool = False
    
    # Story research options
    research_limit: Optional[int] = None
    
    # Text generation options
    text_gen_limit: Optional[int] = None
    
    # Photo research options
    photo_limit: Optional[int] = 5
    
    # Thumbnail options
    use_pro_model: bool = False
    simple_prompt: bool = False


class StartPipelineRequest(BaseModel):
    """Request to start a new pipeline run."""
    config: PipelineConfig = Field(default_factory=PipelineConfig)


class ConfirmPhaseRequest(BaseModel):
    """Request to confirm a phase and continue."""
    rerun: bool = False  # If true, rerun the phase instead of continuing


class PipelineLog(BaseModel):
    """A log entry from pipeline execution."""
    timestamp: datetime
    phase: Optional[PipelinePhase] = None
    level: str = "info"  # info, warning, error
    message: str
    details: Optional[dict[str, Any]] = None

