"""
Thumbnail Generator Worker Adapter.

Wraps the thumbnail_generator module for pipeline integration.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

logger = logging.getLogger(__name__)


class ThumbnailGeneratorWorker:
    """Worker adapter for thumbnail generation phase."""
    
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
                "phase": "thumbnail_generation",
                "status": status,
                "story_id": story_id,
                "data": data or {}
            })
    
    async def run(self, run_id: str, stories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute thumbnail generation for all stories.
        
        Args:
            run_id: Pipeline run ID
            stories: List of story_generation records with research data
        
        Returns:
            Dict with thumbnail generation results
        """
        self._emit_progress("started", data={"total": len(stories)})
        
        if not stories:
            self._emit_progress("completed", data={"completed": 0})
            return {
                "success": True,
                "thumbnails_generated": 0,
                "completed": 0,
                "message": "No stories to generate thumbnails for"
            }
        
        try:
            # Import from thumbnail_generator - adjust path for direct import
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "thumbnail_generator"))
            
            from thumbnail_generator.main import process_story
            from thumbnail_generator import db as thumb_db
            from pipeline_manager.db import get_db_cursor, update_story_status, get_stories_for_run
            
            thumbnails_generated = 0
            completed = 0
            errors = []
            
            # Get story statuses
            story_statuses = {}
            for s in get_stories_for_run(run_id):
                if s.get('story_generation_id'):
                    story_statuses[s['story_generation_id']] = s['id']
            
            for i, story in enumerate(stories):
                if self._cancelled:
                    break
                
                generation_id = str(story['id'])
                title = story.get('hook_title', 'Untitled')
                
                self._emit_progress("running", story_id=generation_id, data={
                    "current": i + 1,
                    "total": len(stories),
                    "title": title,
                    "step": "concepts"
                })
                
                try:
                    # Prepare story data for thumbnail generator
                    story_data = {
                        'generation_id': generation_id,
                        'hook_title': story.get('hook_title', ''),
                        'subtitle': story.get('subtitle', ''),
                        'domain_tag': story.get('domain_tag', ''),
                        'research_data': story.get('research_data', {})
                    }
                    
                    self._emit_progress("running", story_id=generation_id, data={
                        "step": "generating"
                    })
                    
                    # Generate thumbnails (3 concepts)
                    result = process_story(
                        story_data, 
                        use_pro=False,  # Use standard model
                        simple_prompt=False,
                        skip_db=False
                    )
                    
                    thumbnail_ids = result.get('thumbnail_ids', [])
                    thumbnails = result.get('thumbnails', [])
                    
                    # Count successful generations
                    generated_count = sum(1 for t in thumbnails if t.get('status') == 'generated')
                    thumbnails_generated += generated_count
                    
                    # Tag with pipeline run
                    for thumb_id in thumbnail_ids:
                        if thumb_id:
                            with get_db_cursor() as cur:
                                cur.execute("""
                                    UPDATE story_thumbnails SET pipeline_run_id = %s WHERE id = %s
                                """, (run_id, thumb_id))
                    
                    # Auto-select first thumbnail
                    if thumbnail_ids:
                        thumb_db.select_thumbnail(thumbnail_ids[0])
                    
                    # Update story status
                    status_id = story_statuses.get(generation_id)
                    if status_id:
                        update_story_status(status_id, "thumbnail_generation", "completed")
                    
                    completed += 1
                    
                except Exception as e:
                    logger.error(f"Thumbnail generation failed for {title}: {e}")
                    errors.append({"generation_id": generation_id, "title": title, "error": str(e)})
                    
                    status_id = story_statuses.get(generation_id)
                    if status_id:
                        update_story_status(status_id, "thumbnail_generation", "failed")
            
            self._emit_progress("completed", data={
                "completed": completed,
                "thumbnails_generated": thumbnails_generated,
                "errors": len(errors)
            })
            
            return {
                "success": len(errors) == 0,
                "thumbnails_generated": thumbnails_generated,
                "completed": completed,
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Thumbnail generation phase failed: {e}")
            self._emit_progress("failed", data={"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "thumbnails_generated": 0,
                "completed": 0
            }

