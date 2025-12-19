"""
Thumbnail Generator Module

Generates AI cover images for TheBoldUnknown Instagram posts using:
- GPT-5.2 for creative concept generation
- Nano Banana (Google Gemini) for image generation
"""

from .prompt_generator import generate_thumbnail_concepts, generate_single_concept
from .prompt_builder import build_prompt, build_simple_prompt
from .nanobanana import NanoBananaClient, generate_thumbnail
from .preview import generate_preview_html
from .db import (
    get_stories_needing_thumbnails,
    get_story_generation,
    save_thumbnail,
    update_thumbnail_status,
    select_thumbnail,
    get_thumbnails_for_story
)

__all__ = [
    'generate_thumbnail_concepts',
    'generate_single_concept',
    'build_prompt',
    'build_simple_prompt',
    'NanoBananaClient',
    'generate_thumbnail',
    'generate_preview_html',
    'get_stories_needing_thumbnails',
    'get_story_generation',
    'save_thumbnail',
    'update_thumbnail_status',
    'select_thumbnail',
    'get_thumbnails_for_story'
]
