"""
Photo Researcher Worker Adapter.

Wraps the photo_researcher module for pipeline integration.
"""

import asyncio
import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

# Add parent paths for imports
code_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(code_dir))

# Also add photo_researcher directory for internal imports
photo_researcher_dir = code_dir / "photo_researcher"
if str(photo_researcher_dir) not in sys.path:
    sys.path.insert(0, str(photo_researcher_dir))

logger = logging.getLogger(__name__)


class PhotoResearcherWorker:
    """Worker adapter for photo research phase."""
    
    def __init__(
        self,
        progress_callback: Optional[Callable] = None,
        cancellation_check: Optional[Callable[[], bool]] = None,
        pause_event: Optional[asyncio.Event] = None
    ):
        self.progress_callback = progress_callback
        self._cancelled = False
        self._cancellation_check = cancellation_check or (lambda: False)
        self._pause_event = pause_event
    
    def cancel(self):
        """Signal cancellation."""
        self._cancelled = True
    
    def is_cancelled(self) -> bool:
        """Check if we should stop."""
        return self._cancelled or self._cancellation_check()
    
    async def wait_if_paused(self):
        """Block if paused, return True if cancelled during pause."""
        if self._pause_event is None:
            return self.is_cancelled()
        
        while not self._pause_event.is_set():
            if self.is_cancelled():
                return True
            try:
                await asyncio.wait_for(self._pause_event.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
        return self.is_cancelled()
    
    def _emit_progress(self, status: str, story_id: str = None, data: Dict[str, Any] = None):
        """Emit progress update."""
        if self.progress_callback:
            self.progress_callback({
                "phase": "photo_research",
                "status": status,
                "story_id": story_id,
                "data": data or {}
            })
    
    async def run(self, run_id: str, stories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute photo research for all stories.
        
        Args:
            run_id: Pipeline run ID
            stories: List of story_generation records with research data
        
        Returns:
            Dict with photo research results
        """
        self._emit_progress("started", data={"total": len(stories)})
        
        if not stories:
            self._emit_progress("completed", data={"completed": 0})
            return {
                "success": True,
                "photos_found": 0,
                "photos_approved": 0,
                "completed": 0,
                "message": "No stories to find photos for"
            }
        
        try:
            from photo_researcher.generator import QueryGenerator
            from photo_researcher.searcher import ImageSearcher
            from photo_researcher.validator import Validator
            from photo_researcher.analyzer import VisualAnalyzer
            from photo_researcher.scraper import PageScraper
            from photo_researcher.placer import PhotoPlacer
            from photo_researcher.db import Database as PhotoDB
            from pipeline_manager.db import get_db_cursor, update_story_status, get_stories_for_run
            
            generator = QueryGenerator()
            searcher = ImageSearcher()
            validator = Validator()
            analyzer = VisualAnalyzer()
            scraper = PageScraper()
            placer = PhotoPlacer()
            photo_db = PhotoDB()
            
            photos_found = 0
            photos_approved = 0
            completed = 0
            errors = []
            
            # Get story statuses
            story_statuses = {}
            for s in get_stories_for_run(run_id):
                if s.get('story_generation_id'):
                    story_statuses[s['story_generation_id']] = s['id']
            
            for i, story in enumerate(stories):
                # Check cancellation before each item
                if self.is_cancelled():
                    logger.info(f"Photo research cancelled after {completed} items")
                    break
                
                # Wait if paused
                if await self.wait_if_paused():
                    logger.info(f"Photo research cancelled during pause after {completed} items")
                    break
                
                generation_id = str(story['id'])
                research_id = str(story['story_research_id'])
                title = story.get('hook_title', 'Untitled')
                
                self._emit_progress("running", story_id=generation_id, data={
                    "current": i + 1,
                    "total": len(stories),
                    "title": title,
                    "step": "queries"
                })
                
                try:
                    # Define sync function for thread pool
                    def process_story_photos():
                        # Step 1: Generate search queries
                        queries = generator.generate_queries(story)
                        
                        # Step 2: Search and validate
                        valid_candidates = []
                        seen_urls = set()
                        
                        for query in queries:
                            results = searcher.search(query, num_results=5)
                            
                            for res in results:
                                url = res.get('image_url')
                                if url and url not in seen_urls:
                                    seen_urls.add(url)
                                    if validator.check_url(url):
                                        res['search_query'] = query
                                        valid_candidates.append(res)
                        
                        # Step 3: Analyze and save candidates
                        ground_truth = story.get('research_data', {}).get('ground_truth', '')
                        story_photos_found = 0
                        story_photos_approved = 0
                        
                        for candidate in valid_candidates:
                            # Scrape source context
                            source_url = candidate.get('source_page_url')
                            source_context = {}
                            if source_url:
                                source_context = scraper.scrape_context(source_url)
                            
                            # Analyze with vision AI
                            analysis = analyzer.analyze(candidate['image_url'], ground_truth, source_context)
                            candidate.update(analysis)
                            
                            # Store source context
                            if 'metadata' not in candidate:
                                candidate['metadata'] = {}
                            candidate['metadata']['source_context'] = {
                                'title': source_context.get('page_title'),
                                'description': source_context.get('page_description')
                            }
                            
                            # Save to database
                            photo_id = photo_db.save_photo_candidate(research_id, candidate)
                            story_photos_found += 1
                            
                            if candidate.get('status') == 'approved':
                                story_photos_approved += 1
                            
                            # Tag with pipeline run
                            with get_db_cursor() as cur:
                                cur.execute("""
                                    UPDATE story_photos SET pipeline_run_id = %s WHERE id = %s
                                """, (run_id, photo_id))
                        
                        # Step 4: Photo placement
                        try:
                            approved = photo_db.fetch_approved_photos(research_id)
                            slides = story.get('slides', [])
                            
                            if approved and slides:
                                placement = placer.place_photos(
                                    story_title=title,
                                    slides=list(slides),
                                    photos=[dict(p) for p in approved]
                                )
                                
                                if placement:
                                    photo_db.apply_photo_placements(
                                        story_generation_id=generation_id,
                                        placements=placement.get('placements', [])
                                    )
                        except Exception as e:
                            logger.warning(f"Photo placement failed for {title}: {e}")
                        
                        return story_photos_found, story_photos_approved
                    
                    # Run in thread pool to avoid blocking
                    story_photos_found, story_photos_approved = await asyncio.to_thread(process_story_photos)
                    
                    photos_found += story_photos_found
                    photos_approved += story_photos_approved
                    
                    # Update story status
                    status_id = story_statuses.get(generation_id)
                    if status_id:
                        update_story_status(status_id, "photo_research", "completed")
                    
                    completed += 1
                    
                except Exception as e:
                    logger.error(f"Photo research failed for {title}: {e}")
                    errors.append({"generation_id": generation_id, "title": title, "error": str(e)})
                    
                    status_id = story_statuses.get(generation_id)
                    if status_id:
                        update_story_status(status_id, "photo_research", "failed")
            
            photo_db.close()
            
            self._emit_progress("completed", data={
                "completed": completed,
                "photos_found": photos_found,
                "photos_approved": photos_approved,
                "errors": len(errors)
            })
            
            return {
                "success": len(errors) == 0,
                "photos_found": photos_found,
                "photos_approved": photos_approved,
                "completed": completed,
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Photo research phase failed: {e}")
            self._emit_progress("failed", data={"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "photos_found": 0,
                "photos_approved": 0,
                "completed": 0
            }

