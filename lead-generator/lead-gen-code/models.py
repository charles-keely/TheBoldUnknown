from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class ProcessingStatus(str, Enum):
    NEW = "new"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"

class LeadCandidate(BaseModel):
    title: str
    url: str
    summary: str
    source_origin: str
    published_at: Optional[datetime] = Field(default_factory=datetime.now)
    
    # Enrichment fields
    embedding: Optional[List[float]] = None
    virality_score: int = 0
    viral_hook: str = ""  # The shareable angle identified during virality check
    brand_score: int = 0
    brand_reasoning: str = ""
    new_topics: List[str] = Field(default_factory=list)
    
    status: ProcessingStatus = ProcessingStatus.NEW

    class Config:
        arbitrary_types_allowed = True
