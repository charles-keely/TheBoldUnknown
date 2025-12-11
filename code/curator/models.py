from pydantic import BaseModel
from typing import List, Optional

class CuratedStory(BaseModel):
    id: str
    title: str
    reasoning: str

class CurationResult(BaseModel):
    selected_stories: List[CuratedStory]
    week_balance_notes: str
    missing_topics_suggestions: Optional[str] = None

