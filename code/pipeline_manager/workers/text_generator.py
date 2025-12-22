"""
Text Generator Worker Adapter.

Wraps the text_generator module for pipeline integration.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

# Add parent paths for imports
code_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(code_dir))

# Also add text_generator directory for internal imports (has bare imports like 'from utils import ...')
text_gen_dir = code_dir / "text_generator"
if str(text_gen_dir) not in sys.path:
    sys.path.insert(0, str(text_gen_dir))

logger = logging.getLogger(__name__)


class TextGeneratorWorker:
    """Worker adapter for text generation phase."""
    
    def __init__(self, progress_callback: Optional[Callable] = None):
        self.progress_callback = progress_callback
        self._cancelled = False
    
    def cancel(self):
        """Signal cancellation."""
        self._cancelled = True
    
    def _emit_progress(self, status: str, story_id: str = None, data: Dict[str, Any] = None):
        """Emit progress update."""
        if self.progress_callback:
            self.progress_callback({
                "phase": "text_generation",
                "status": status,
                "story_id": story_id,
                "data": data or {}
            })
    
    async def run(self, run_id: str, research_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute text generation for all researched stories.
        
        Args:
            run_id: Pipeline run ID
            research_items: List of story_research records
        
        Returns:
            Dict with generation results
        """
        self._emit_progress("started", data={"total": len(research_items)})
        
        if not research_items:
            self._emit_progress("completed", data={"completed": 0})
            return {
                "success": True,
                "generation_ids": [],
                "completed": 0,
                "message": "No stories to generate text for"
            }
        
        try:
            from text_generator.generator import (
                generate_story_slides, 
                generate_cover_options,
                generate_instagram_caption,
                generate_hashtags
            )
            from text_generator.db import (
                save_story_generation,
                save_story_slides,
                update_caption_and_hashtags
            )
            from pipeline_manager.db import link_generation_to_run, update_story_status, get_stories_for_run
            
            generation_ids = []
            completed = 0
            errors = []
            
            # Get story statuses for this run
            story_statuses = {}
            for s in get_stories_for_run(run_id):
                if s.get('story_research_id'):
                    story_statuses[s['story_research_id']] = s['id']
            
            for i, research in enumerate(research_items):
                if self._cancelled:
                    break
                
                research_id = str(research['id'])
                title = research.get('title', 'Untitled')
                
                self._emit_progress("running", story_id=research_id, data={
                    "current": i + 1,
                    "total": len(research_items),
                    "title": title,
                    "step": "slides"
                })
                
                try:
                    # Get research data
                    research_data = research.get('research_data', {})
                    ground_truth = research_data.get('ground_truth', '')
                    follow_up = research_data.get('follow_up', {})
                    
                    # Build research text for the generator
                    research_text = ground_truth
                    if follow_up and follow_up.get('answer'):
                        research_text += f"\n\nFollow-up Research:\n{follow_up['answer']}"
                    
                    # Step 1: Generate slides
                    slides_result = generate_story_slides(research_text)
                    slides = slides_result.get('slides', [])
                    
                    self._emit_progress("running", story_id=research_id, data={
                        "step": "cover",
                        "slides_generated": len(slides)
                    })
                    
                    # Step 2: Generate cover options
                    cover_result = generate_cover_options(research_text, slides)
                    options = cover_result.get('options', [])
                    selected_id = cover_result.get('selected_id', 1)
                    
                    # Find selected option
                    selected_option = next((o for o in options if o.get('id') == selected_id), options[0] if options else {})
                    
                    self._emit_progress("running", story_id=research_id, data={
                        "step": "caption"
                    })
                    
                    # Step 3: Generate caption
                    caption_result = generate_instagram_caption(slides, selected_option)
                    caption = caption_result.get('caption', '')
                    
                    self._emit_progress("running", story_id=research_id, data={
                        "step": "hashtags"
                    })
                    
                    # Step 4: Generate hashtags
                    hashtags_result = generate_hashtags(slides, selected_option)
                    hashtags = hashtags_result.get('hashtags', [])
                    
                    # Save to database
                    selected_data = {
                        'title': selected_option.get('title', 'Untitled'),
                        'subtitle': selected_option.get('subtitle', ''),
                        'domain_tag': selected_option.get('domain_tag', 'UNKNOWN')
                    }
                    full_generation_data = {
                        'options': options,
                        'selected_id': selected_id,
                        'reasoning': cover_result.get('reasoning', '')
                    }
                    
                    generation_id = save_story_generation(
                        research_id,
                        selected_data,
                        full_generation_data
                    )
                    
                    # Save slides
                    save_story_slides(generation_id, slides)
                    
                    # Update caption and hashtags
                    update_caption_and_hashtags(generation_id, caption, hashtags)
                    
                    # Link to pipeline run
                    link_generation_to_run(generation_id, run_id)
                    
                    # Update story status
                    status_id = story_statuses.get(research_id)
                    if status_id:
                        update_story_status(status_id, "text_generation", "completed",
                                          story_generation_id=generation_id)
                    
                    generation_ids.append(generation_id)
                    completed += 1
                    
                except Exception as e:
                    logger.error(f"Text generation failed for {title}: {e}")
                    errors.append({"research_id": research_id, "title": title, "error": str(e)})
                    
                    status_id = story_statuses.get(research_id)
                    if status_id:
                        update_story_status(status_id, "text_generation", "failed")
            
            self._emit_progress("completed", data={
                "completed": completed,
                "errors": len(errors)
            })
            
            return {
                "success": len(errors) == 0,
                "generation_ids": generation_ids,
                "completed": completed,
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Text generation phase failed: {e}")
            self._emit_progress("failed", data={"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "generation_ids": [],
                "completed": 0
            }

