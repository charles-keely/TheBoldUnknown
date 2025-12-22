"""
Story Researcher Worker Adapter.

Wraps the story_researcher module for pipeline integration.
"""

import asyncio
import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
import uuid

# Add parent paths for imports
code_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(code_dir))

# Also add story_researcher directory for internal imports
story_researcher_dir = code_dir / "story_researcher"
if str(story_researcher_dir) not in sys.path:
    sys.path.insert(0, str(story_researcher_dir))

logger = logging.getLogger(__name__)


class StoryResearcherWorker:
    """Worker adapter for story research phase."""
    
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
                "phase": "story_research",
                "status": status,
                "story_id": story_id,
                "data": data or {}
            })
    
    async def run(self, run_id: str, leads: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute story research for all leads.
        
        Args:
            run_id: Pipeline run ID
            leads: List of curated leads to research
        
        Returns:
            Dict with research results
        """
        self._emit_progress("started", data={"total": len(leads)})
        
        if not leads:
            self._emit_progress("completed", data={"completed": 0})
            return {
                "success": True,
                "research_ids": [],
                "completed": 0,
                "message": "No leads to research"
            }
        
        try:
            from story_researcher.researcher import Researcher
            from story_researcher.db import Database as ResearchDB
            from pipeline_manager.db import link_research_to_run, update_story_status, get_stories_for_run, get_db_cursor
            
            researcher = Researcher()
            research_db = ResearchDB()
            
            research_ids = []
            completed = 0
            errors = []
            
            # Get story statuses for this run
            story_statuses = {str(s['lead_id']): s['id'] for s in get_stories_for_run(run_id) if s.get('lead_id')}
            
            for i, lead in enumerate(leads):
                if self._cancelled:
                    break
                
                lead_id = str(lead['id'])
                title = lead.get('title', 'Untitled')
                
                self._emit_progress("running", story_id=lead_id, data={
                    "current": i + 1,
                    "total": len(leads),
                    "title": title
                })
                
                try:
                    # Execute research
                    story_data = {
                        "title": lead.get("title"),
                        "url": lead.get("url"),
                        "summary": lead.get("summary")
                    }
                    
                    result = await asyncio.to_thread(researcher.research_story, story_data)
                    
                    # Create research entry in database
                    with get_db_cursor() as cur:
                        cur.execute("""
                            INSERT INTO story_research (lead_id, status, notes)
                            VALUES (%s, 'in_progress', '')
                            RETURNING id
                        """, (lead_id,))
                        research_id = str(cur.fetchone()['id'])
                    
                    # Update with research results
                    research_db.update_research_results(research_id, result, 'completed')
                    
                    # Link to pipeline run
                    link_research_to_run(research_id, run_id)
                    
                    # Update story status
                    status_id = story_statuses.get(lead_id)
                    if status_id:
                        update_story_status(status_id, "story_research", "completed", 
                                          story_research_id=research_id)
                    
                    research_ids.append(research_id)
                    completed += 1
                    
                except Exception as e:
                    logger.error(f"Research failed for {title}: {e}")
                    errors.append({"lead_id": lead_id, "title": title, "error": str(e)})
                    
                    # Update story status to failed
                    status_id = story_statuses.get(lead_id)
                    if status_id:
                        update_story_status(status_id, "story_research", "failed")
            
            self._emit_progress("completed", data={
                "completed": completed,
                "errors": len(errors)
            })
            
            return {
                "success": len(errors) == 0,
                "research_ids": research_ids,
                "completed": completed,
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Story research phase failed: {e}")
            self._emit_progress("failed", data={"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "research_ids": [],
                "completed": 0
            }

