"""
Worker adapters for pipeline phases.

Each worker wraps an existing CLI-based module, calling its core functions
directly for better error capture, progress callbacks, and graceful cancellation.
"""

from .lead_generator import LeadGeneratorWorker
from .curator import CuratorWorker
from .story_researcher import StoryResearcherWorker
from .text_generator import TextGeneratorWorker
from .photo_researcher import PhotoResearcherWorker
from .thumbnail_generator import ThumbnailGeneratorWorker

__all__ = [
    "LeadGeneratorWorker",
    "CuratorWorker",
    "StoryResearcherWorker",
    "TextGeneratorWorker",
    "PhotoResearcherWorker",
    "ThumbnailGeneratorWorker",
]

