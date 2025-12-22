"""
Curator Worker Adapter.

Wraps the curator module for pipeline integration.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

# Add parent paths for imports
code_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(code_dir))

# Also add curator directory for internal imports
curator_dir = code_dir / "curator"
if str(curator_dir) not in sys.path:
    sys.path.insert(0, str(curator_dir))

logger = logging.getLogger(__name__)


class CuratorWorker:
    """Worker adapter for curation phase."""
    
    def __init__(self, progress_callback: Optional[Callable] = None):
        self.progress_callback = progress_callback
        self._cancelled = False
    
    def cancel(self):
        """Signal cancellation."""
        self._cancelled = True
    
    def _emit_progress(self, status: str, data: Dict[str, Any] = None):
        """Emit progress update."""
        if self.progress_callback:
            self.progress_callback({
                "phase": "curation",
                "status": status,
                "data": data or {}
            })
    
    async def run(self, run_id: str, candidates: List[Dict[str, Any]], target_count: int = 21) -> Dict[str, Any]:
        """
        Execute curation to select best stories.
        
        Args:
            run_id: Pipeline run ID
            candidates: List of lead candidates to curate
            target_count: Number of stories to select
        
        Returns:
            Dict with selected story IDs and reasoning
        """
        self._emit_progress("started", {"candidates": len(candidates)})
        
        if not candidates:
            self._emit_progress("completed", {"selected": 0})
            return {
                "success": True,
                "selected_ids": [],
                "selected_count": 0,
                "message": "No candidates to curate"
            }
        
        try:
            from curator.logic import CuratorLogic
            from pipeline_manager.db import get_db_cursor
            
            curator = CuratorLogic()
            
            self._emit_progress("running", {"message": "AI curator selecting stories..."})
            
            # Run curation (honor requested target_count)
            result = curator.curate_stories(candidates, target_count=target_count)
            
            selected_ids = []
            selected_stories = []
            
            for story in result.selected_stories:
                selected_ids.append(story.id)
                selected_stories.append({
                    "id": story.id,
                    "title": story.title,
                    "reasoning": story.reasoning
                })
                
                # Update lead status to 'approved' (matches DB constraint: new/approved/rejected/published)
                with get_db_cursor() as cur:
                    cur.execute("""
                        UPDATE leads SET status = 'approved' WHERE id = %s
                    """, (story.id,))
            
            self._emit_progress("completed", {
                "selected": len(selected_ids),
                "balance_notes": result.week_balance_notes
            })
            
            return {
                "success": True,
                "selected_ids": selected_ids,
                "selected_count": len(selected_ids),
                "selected_stories": selected_stories,
                "week_balance_notes": result.week_balance_notes,
                "missing_topics": result.missing_topics_suggestions
            }
            
        except Exception as e:
            logger.error(f"Curation failed: {e}")
            self._emit_progress("failed", {"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "selected_ids": [],
                "selected_count": 0
            }

