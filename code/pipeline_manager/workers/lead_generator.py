"""
Lead Generator Worker Adapter.

Wraps the lead_generator module for pipeline integration.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

# Add parent paths for imports
code_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(code_dir))

# Also add lead_generator directory for its internal relative imports
lead_gen_dir = code_dir / "lead_generator"
if str(lead_gen_dir) not in sys.path:
    sys.path.insert(0, str(lead_gen_dir))

logger = logging.getLogger(__name__)


class LeadGeneratorWorker:
    """Worker adapter for lead generation phase."""
    
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
                "phase": "lead_generation",
                "status": status,
                "data": data or {}
            })
    
    async def run(self, run_id: str, source: str = "all") -> Dict[str, Any]:
        """
        Execute lead generation workflow.
        
        Args:
            run_id: Pipeline run ID to tag generated leads
            source: Source to scan ("all", "rss", "perplexity")
        
        Returns:
            Dict with results including lead IDs and stats
        """
        self._emit_progress("started")
        
        try:
            # Import lead generator components
            from lead_generator.logic.workflow import Workflow
            from lead_generator.database import db as lead_db
            
            workflow = Workflow()
            
            # Track leads created in this run (lead_generator Database doesn't expose get_all_leads)
            # so we diff against a minimal SELECT.
            leads_before: set[str] = set()
            try:
                existing = lead_db.fetch_all("SELECT id FROM leads")
                leads_before = {str(l["id"]) for l in (existing or [])}
            except Exception:
                # If the table doesn't exist yet or DB hiccups, we still run; we'll just skip diffing.
                leads_before = set()
            
            self._emit_progress("running", {"message": "Scanning RSS feeds and discovery..."})
            
            # Run the workflow
            workflow.run(source=source)
            
            # Find newly created leads
            all_leads = lead_db.fetch_all("SELECT id, title, url, summary, brand_score, virality_score, source_origin, published_at, status FROM leads")
            new_leads = [l for l in (all_leads or []) if str(l["id"]) not in leads_before]
            
            # Tag new leads with pipeline_run_id
            from pipeline_manager.db import link_lead_to_run, create_story_status
            
            lead_ids = []
            for lead in new_leads:
                lead_id = str(lead['id'])
                link_lead_to_run(lead_id, run_id)
                create_story_status(run_id, lead_id, lead.get('title', 'Untitled'))
                lead_ids.append(lead_id)
            
            self._emit_progress("completed", {
                "leads_discovered": len(new_leads),
                "lead_ids": lead_ids
            })
            
            return {
                "success": True,
                "leads_discovered": len(new_leads),
                "lead_ids": lead_ids,
                "leads": new_leads
            }
            
        except Exception as e:
            logger.error(f"Lead generation failed: {e}")
            self._emit_progress("failed", {"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "leads_discovered": 0,
                "lead_ids": []
            }

