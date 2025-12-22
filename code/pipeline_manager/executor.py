"""
Pipeline Executor - Orchestration logic for running the content pipeline.

Handles both Auto Mode (full pipeline) and Step Mode (phase-by-phase with approval).
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from .models import (
    PipelineMode, PipelineStatus, PhaseStatus, PipelinePhase,
    PipelineStats, PhaseProgress
)
from .db import (
    get_pipeline_run, update_pipeline_run, update_pipeline_stats, update_phase_status,
    get_leads_for_run, get_research_for_run, get_generations_for_run,
    get_stories_for_run, get_pending_leads_for_curation, get_curated_leads_for_research,
    get_phase1_data, get_phase2_data, get_phase3_data, get_phase4_data, get_phase5_data
)
from .workers import (
    LeadGeneratorWorker,
    CuratorWorker,
    StoryResearcherWorker,
    TextGeneratorWorker,
    PhotoResearcherWorker,
    ThumbnailGeneratorWorker
)
from .config import config

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry logic."""
    max_retries: int = 3
    base_delay: float = 2.0
    max_delay: float = 60.0
    exponential_base: float = 2.0


class CancellationError(Exception):
    """Raised when a pipeline run is cancelled."""
    pass


class PipelineExecutor:
    """
    Orchestrates pipeline execution with support for auto and step modes.
    
    The executor runs as an async background task and can be paused, resumed, or cancelled.
    All state is persisted to the database for session recovery.
    """
    
    def __init__(self, run_id: str, progress_callback: Optional[Callable] = None, run_config: Dict[str, Any] = None):
        self.run_id = run_id
        self.progress_callback = progress_callback
        self.run_config = run_config or {}
        self._cancelled = False
        self._paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused by default
        self._task: Optional[asyncio.Task] = None
        self._active_workers: List[Any] = []  # Track workers for cancellation propagation
        self.retry_config = RetryConfig(
            max_retries=config.max_retries,
            base_delay=config.retry_base_delay,
            max_delay=config.retry_max_delay
        )
    
    def set_task(self, task: asyncio.Task):
        """Store reference to the asyncio Task running this executor."""
        self._task = task
    
    def cancel(self):
        """Signal cancellation of this run and cancel the running task."""
        self._cancelled = True
        logger.info(f"Pipeline run {self.run_id} marked for cancellation")
        
        # Cancel all active workers
        for worker in self._active_workers:
            if hasattr(worker, 'cancel'):
                worker.cancel()
        
        # Cancel the asyncio task itself (raises CancelledError)
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info(f"Pipeline run {self.run_id} task cancelled")
    
    def pause(self):
        """Pause execution - workers will block at next checkpoint."""
        self._paused = True
        self._pause_event.clear()  # Block waiters
        logger.info(f"Pipeline run {self.run_id} PAUSED - pause_event cleared, workers will block")
    
    def resume(self):
        """Resume paused execution."""
        was_paused = self._paused
        self._paused = False
        self._pause_event.set()  # Unblock waiters
        logger.info(f"Pipeline run {self.run_id} RESUMED - pause_event set (was_paused={was_paused})")
    
    async def wait_if_paused(self):
        """Block until resumed if currently paused. Returns True if cancelled."""
        while not self._pause_event.is_set():
            # Check for cancellation while paused
            if self._cancelled:
                return True
            try:
                await asyncio.wait_for(self._pause_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
        return self._cancelled
    
    async def check_cancelled(self) -> bool:
        """Check if this run has been cancelled."""
        if self._cancelled:
            return True
        
        # Also check database status
        run = get_pipeline_run(self.run_id)
        if run and run.get('status') == 'cancelled':
            self._cancelled = True
            return True
        
        return False
    
    async def check_paused(self) -> bool:
        """Check if this run is paused."""
        if self._paused:
            return True
        
        run = get_pipeline_run(self.run_id)
        if run and run.get('status') == 'paused':
            self._paused = True
            self._pause_event.clear()
            return True
        
        return False
    
    def register_worker(self, worker):
        """Register a worker so we can cancel it on pipeline cancellation."""
        self._active_workers.append(worker)
    
    def unregister_worker(self, worker):
        """Unregister a worker when it completes."""
        if worker in self._active_workers:
            self._active_workers.remove(worker)
    
    def _emit_progress(self, data: Dict[str, Any]):
        """Emit progress update via callback."""
        if self.progress_callback:
            try:
                self.progress_callback(data)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")
    
    def _worker_progress_callback(self, update: Dict[str, Any]):
        """Handle progress updates from workers."""
        phase = update.get('phase')
        status = update.get('status')
        data = update.get('data', {})
        event_type = update.get('event_type', 'phase_update')
        
        # Update phase status in database
        if status in ('started', 'running', 'completed', 'failed'):
            db_status = 'running' if status in ('started', 'running') else status
            update_phase_status(self.run_id, phase, db_status, **data)
        
        # Emit to UI with specific event type
        self._emit_progress({
            "event": event_type,
            "run_id": self.run_id,
            "phase": phase,
            "status": status,
            "data": data
        })
    
    def _emit_story_event(self, phase: str, story_id: str, title: str, status: str, data: Dict[str, Any] = None):
        """Emit a story-specific event."""
        self._emit_progress({
            "event": "story_update",
            "run_id": self.run_id,
            "phase": phase,
            "story_id": story_id,
            "title": title,
            "status": status,
            "data": data or {}
        })
    
    def _emit_phase_progress(self, phase: str, step: str, progress: int, message: str, stats: Dict[str, Any] = None):
        """Emit phase progress update with sub-step details."""
        self._emit_progress({
            "event": "phase_progress",
            "run_id": self.run_id,
            "phase": phase,
            "step": step,
            "progress": progress,
            "message": message,
            "stats": stats or {}
        })
    
    def _emit_item_event(self, event_type: str, phase: str, story_id: str, item_data: Dict[str, Any]):
        """Emit an item-level event (photo found, thumbnail generated, etc.)."""
        self._emit_progress({
            "event": event_type,
            "run_id": self.run_id,
            "phase": phase,
            "story_id": story_id,
            **item_data
        })
    
    async def run_auto_mode(self) -> Dict[str, Any]:
        """
        Execute the full pipeline in auto mode.
        
        Runs all phases sequentially without user intervention.
        """
        logger.info(f"Starting auto mode pipeline run {self.run_id}")
        
        update_pipeline_run(
            self.run_id,
            status='running',
            started_at=datetime.utcnow(),
            current_phase='lead_generation',
            current_phase_index=1
        )
        
        try:
            # Phase 1: Lead Generation + Curation
            await self._run_phase_1_leads()
            
            if await self.check_cancelled() or await self.wait_if_paused():
                raise CancellationError("Pipeline cancelled")
            
            # Phase 2: Story Research
            await self._run_phase_2_research()
            
            if await self.check_cancelled() or await self.wait_if_paused():
                raise CancellationError("Pipeline cancelled")
            
            # Phase 3: Text Generation
            await self._run_phase_3_text()
            
            if await self.check_cancelled() or await self.wait_if_paused():
                raise CancellationError("Pipeline cancelled")
            
            # Phase 4: Photo Research
            await self._run_phase_4_photos()
            
            if await self.check_cancelled() or await self.wait_if_paused():
                raise CancellationError("Pipeline cancelled")
            
            # Phase 5: Thumbnail Generation
            await self._run_phase_5_thumbnails()
            
            # Complete!
            update_pipeline_run(
                self.run_id,
                status='completed',
                completed_at=datetime.utcnow()
            )
            
            self._emit_progress({
                "event": "pipeline_complete",
                "run_id": self.run_id,
                "status": "completed"
            })
            
            return {"success": True, "status": "completed"}
            
        except asyncio.CancelledError:
            # Asyncio task was cancelled - this is a hard stop
            logger.info(f"Pipeline run {self.run_id} task was cancelled")
            update_pipeline_run(self.run_id, status='cancelled', completed_at=datetime.utcnow())
            return {"success": False, "status": "cancelled"}
            
        except CancellationError:
            logger.info(f"Pipeline run {self.run_id} was cancelled")
            update_pipeline_run(self.run_id, status='cancelled', completed_at=datetime.utcnow())
            return {"success": False, "status": "cancelled"}
            
        except Exception as e:
            logger.error(f"Pipeline run {self.run_id} failed: {e}")
            update_pipeline_run(
                self.run_id,
                status='failed',
                error_message=str(e),
                completed_at=datetime.utcnow()
            )
            
            self._emit_progress({
                "event": "pipeline_error",
                "run_id": self.run_id,
                "error": str(e)
            })
            
            return {"success": False, "status": "failed", "error": str(e)}
    
    async def run_step_mode_phase(self, phase: str) -> Dict[str, Any]:
        """
        Execute a single phase in step mode.
        
        Args:
            phase: Phase identifier to execute
        
        Returns:
            Phase execution result
        """
        logger.info(f"Running phase {phase} for pipeline {self.run_id}")
        
        update_pipeline_run(
            self.run_id,
            status='running',
            current_phase=phase
        )
        
        try:
            if phase == 'lead_generation':
                result = await self._run_phase_1_leads()
            elif phase == 'story_research':
                result = await self._run_phase_2_research()
            elif phase == 'text_generation':
                result = await self._run_phase_3_text()
            elif phase == 'photo_research':
                result = await self._run_phase_4_photos()
            elif phase == 'thumbnail_generation':
                result = await self._run_phase_5_thumbnails()
            else:
                raise ValueError(f"Unknown phase: {phase}")
            
            # Pause after phase completion in step mode
            update_pipeline_run(self.run_id, status='paused')
            
            return result
            
        except Exception as e:
            logger.error(f"Phase {phase} failed: {e}")
            update_phase_status(self.run_id, phase, 'failed', error_message=str(e))
            raise
    
    # =========================================================================
    # Phase Implementations
    # =========================================================================
    
    async def _run_phase_1_leads(self) -> Dict[str, Any]:
        """Phase 1: Lead Generation + Curation."""
        update_pipeline_run(self.run_id, current_phase='lead_generation', current_phase_index=1)
        update_phase_status(self.run_id, 'lead_generation', 'running', started_at=datetime.utcnow())
        
        # Step 1a: Lead Generation
        lead_worker = LeadGeneratorWorker(
            progress_callback=self._worker_progress_callback,
            cancellation_check=lambda: self._cancelled,
            pause_event=self._pause_event
        )
        self.register_worker(lead_worker)
        source = self.run_config.get("source", "all")
        
        try:
            lead_result = await lead_worker.run(self.run_id, source=source)
        finally:
            self.unregister_worker(lead_worker)
        
        if self._cancelled:
            raise CancellationError("Pipeline cancelled during lead generation")
        
        if not lead_result.get('success'):
            update_phase_status(self.run_id, 'lead_generation', 'failed', 
                              error_message=lead_result.get('error'))
            raise Exception(f"Lead generation failed: {lead_result.get('error')}")
        
        leads_discovered = lead_result.get('leads_discovered', 0)
        leads = lead_result.get('leads', [])
        
        # Step 1b: Curation (select best stories)
        if leads and not self._cancelled:
            curator_worker = CuratorWorker(
                progress_callback=self._worker_progress_callback,
                cancellation_check=lambda: self._cancelled,
                pause_event=self._pause_event
            )
            self.register_worker(curator_worker)
            # Use story_count from run config, fallback to global config
            target_count = self.run_config.get('story_count', config.curation_story_count)
            
            try:
                curation_result = await curator_worker.run(self.run_id, leads, target_count=target_count)
            finally:
                self.unregister_worker(curator_worker)
            
            leads_approved = curation_result.get('selected_count', 0)
        else:
            leads_approved = 0
        
        if self._cancelled:
            raise CancellationError("Pipeline cancelled during curation")
        
        # Update stats
        update_pipeline_stats(self.run_id, {
            'leads_discovered': leads_discovered,
            'leads_approved': leads_approved
        })
        
        update_phase_status(self.run_id, 'lead_generation', 'completed', 
                          completed_at=datetime.utcnow(),
                          total_items=leads_discovered,
                          completed_items=leads_approved)
        
        # Emit phase complete with full phase data
        phase_data = get_phase1_data(self.run_id)
        self._emit_progress({
            "event": "phase_complete",
            "run_id": self.run_id,
            "phase": "lead_generation",
            "stats": {
                "leads_discovered": leads_discovered,
                "leads_approved": leads_approved
            },
            "data": phase_data
        })
        
        return {
            "phase": "lead_generation",
            "success": True,
            "leads_discovered": leads_discovered,
            "leads_approved": leads_approved
        }
    
    async def _run_phase_2_research(self) -> Dict[str, Any]:
        """Phase 2: Story Research."""
        update_pipeline_run(self.run_id, current_phase='story_research', current_phase_index=2)
        update_phase_status(self.run_id, 'story_research', 'running', started_at=datetime.utcnow())
        
        # Get approved leads for this run that haven't been researched yet
        # (DB constraint supports: new/approved/rejected/published)
        curated_leads = get_curated_leads_for_research(self.run_id)
        
        if not curated_leads:
            update_phase_status(self.run_id, 'story_research', 'completed',
                              completed_at=datetime.utcnow(),
                              total_items=0, completed_items=0)
            return {"phase": "story_research", "success": True, "completed": 0}
        
        research_worker = StoryResearcherWorker(
            progress_callback=self._worker_progress_callback,
            cancellation_check=lambda: self._cancelled,
            pause_event=self._pause_event
        )
        self.register_worker(research_worker)
        
        try:
            result = await research_worker.run(self.run_id, curated_leads)
        finally:
            self.unregister_worker(research_worker)
        
        # Check if we were cancelled mid-phase
        if self._cancelled:
            raise CancellationError("Pipeline cancelled during story research")
        
        if not result.get('success') and result.get('completed', 0) == 0:
            update_phase_status(self.run_id, 'story_research', 'failed',
                              error_message=result.get('error'))
            raise Exception(f"Story research failed: {result.get('error')}")
        
        research_completed = result.get('completed', 0)
        
        update_pipeline_stats(self.run_id, {'research_completed': research_completed})
        update_phase_status(self.run_id, 'story_research', 'completed',
                          completed_at=datetime.utcnow(),
                          total_items=len(curated_leads),
                          completed_items=research_completed)
        
        # Emit phase complete with full phase data
        phase_data = get_phase2_data(self.run_id)
        self._emit_progress({
            "event": "phase_complete",
            "run_id": self.run_id,
            "phase": "story_research",
            "stats": {"research_completed": research_completed},
            "data": phase_data
        })
        
        return {
            "phase": "story_research",
            "success": True,
            "completed": research_completed
        }
    
    async def _run_phase_3_text(self) -> Dict[str, Any]:
        """Phase 3: Text Generation."""
        update_pipeline_run(self.run_id, current_phase='text_generation', current_phase_index=3)
        update_phase_status(self.run_id, 'text_generation', 'running', started_at=datetime.utcnow())
        
        # Get researched stories for this run
        research_items = get_research_for_run(self.run_id)
        completed_research = [r for r in research_items if r.get('status') == 'completed']
        
        if not completed_research:
            update_phase_status(self.run_id, 'text_generation', 'completed',
                              completed_at=datetime.utcnow(),
                              total_items=0, completed_items=0)
            return {"phase": "text_generation", "success": True, "completed": 0}
        
        text_worker = TextGeneratorWorker(
            progress_callback=self._worker_progress_callback,
            cancellation_check=lambda: self._cancelled,
            pause_event=self._pause_event
        )
        self.register_worker(text_worker)
        
        try:
            result = await text_worker.run(self.run_id, completed_research)
        finally:
            self.unregister_worker(text_worker)
        
        if self._cancelled:
            raise CancellationError("Pipeline cancelled during text generation")
        
        if not result.get('success') and result.get('completed', 0) == 0:
            update_phase_status(self.run_id, 'text_generation', 'failed',
                              error_message=result.get('error'))
            raise Exception(f"Text generation failed: {result.get('error')}")
        
        generations_completed = result.get('completed', 0)
        
        update_pipeline_stats(self.run_id, {'generations_completed': generations_completed})
        update_phase_status(self.run_id, 'text_generation', 'completed',
                          completed_at=datetime.utcnow(),
                          total_items=len(completed_research),
                          completed_items=generations_completed)
        
        # Emit phase complete with full phase data
        phase_data = get_phase3_data(self.run_id)
        self._emit_progress({
            "event": "phase_complete",
            "run_id": self.run_id,
            "phase": "text_generation",
            "stats": {"generations_completed": generations_completed},
            "data": phase_data
        })
        
        return {
            "phase": "text_generation",
            "success": True,
            "completed": generations_completed
        }
    
    async def _run_phase_4_photos(self) -> Dict[str, Any]:
        """Phase 4: Photo Research."""
        update_pipeline_run(self.run_id, current_phase='photo_research', current_phase_index=4)
        update_phase_status(self.run_id, 'photo_research', 'running', started_at=datetime.utcnow())
        
        # Get story generations for this run
        generations = get_generations_for_run(self.run_id)
        
        if not generations:
            update_phase_status(self.run_id, 'photo_research', 'completed',
                              completed_at=datetime.utcnow(),
                              total_items=0, completed_items=0)
            return {"phase": "photo_research", "success": True, "completed": 0}
        
        photo_worker = PhotoResearcherWorker(
            progress_callback=self._worker_progress_callback,
            cancellation_check=lambda: self._cancelled,
            pause_event=self._pause_event
        )
        self.register_worker(photo_worker)
        
        try:
            result = await photo_worker.run(self.run_id, generations)
        finally:
            self.unregister_worker(photo_worker)
        
        if self._cancelled:
            raise CancellationError("Pipeline cancelled during photo research")
        
        photos_found = result.get('photos_found', 0)
        photos_approved = result.get('photos_approved', 0)
        completed = result.get('completed', 0)
        
        update_pipeline_stats(self.run_id, {
            'photos_found': photos_found,
            'photos_approved': photos_approved
        })
        update_phase_status(self.run_id, 'photo_research', 'completed',
                          completed_at=datetime.utcnow(),
                          total_items=len(generations),
                          completed_items=completed)
        
        # Emit phase complete with full phase data
        phase_data = get_phase4_data(self.run_id)
        self._emit_progress({
            "event": "phase_complete",
            "run_id": self.run_id,
            "phase": "photo_research",
            "stats": {
                "photos_found": photos_found,
                "photos_approved": photos_approved
            },
            "data": phase_data
        })
        
        return {
            "phase": "photo_research",
            "success": True,
            "completed": completed,
            "photos_found": photos_found,
            "photos_approved": photos_approved
        }
    
    async def _run_phase_5_thumbnails(self) -> Dict[str, Any]:
        """Phase 5: Thumbnail Generation."""
        update_pipeline_run(self.run_id, current_phase='thumbnail_generation', current_phase_index=5)
        update_phase_status(self.run_id, 'thumbnail_generation', 'running', started_at=datetime.utcnow())
        
        # Get story generations for this run
        generations = get_generations_for_run(self.run_id)
        
        if not generations:
            update_phase_status(self.run_id, 'thumbnail_generation', 'completed',
                              completed_at=datetime.utcnow(),
                              total_items=0, completed_items=0)
            return {"phase": "thumbnail_generation", "success": True, "completed": 0}
        
        thumb_worker = ThumbnailGeneratorWorker(
            progress_callback=self._worker_progress_callback,
            cancellation_check=lambda: self._cancelled,
            pause_event=self._pause_event
        )
        self.register_worker(thumb_worker)
        
        try:
            result = await thumb_worker.run(self.run_id, generations)
        finally:
            self.unregister_worker(thumb_worker)
        
        if self._cancelled:
            raise CancellationError("Pipeline cancelled during thumbnail generation")
        
        thumbnails_generated = result.get('thumbnails_generated', 0)
        completed = result.get('completed', 0)
        errors = result.get("errors") or []

        # If nothing completed and we have an error, fail the phase (like other phases).
        if (not result.get("success")) and completed == 0:
            error_message = (result.get("error") or (errors[0].get("error") if isinstance(errors, list) and errors else "Thumbnail generation failed"))
            update_phase_status(self.run_id, 'thumbnail_generation', 'failed', error_message=error_message)
            raise Exception(f"Thumbnail generation failed: {error_message}")
        
        update_pipeline_stats(self.run_id, {'thumbnails_generated': thumbnails_generated})
        update_phase_status(self.run_id, 'thumbnail_generation', 'completed',
                          completed_at=datetime.utcnow(),
                          total_items=len(generations),
                          completed_items=completed)
        
        # Emit phase complete with full phase data
        phase_data = get_phase5_data(self.run_id)
        self._emit_progress({
            "event": "phase_complete",
            "run_id": self.run_id,
            "phase": "thumbnail_generation",
            "stats": {"thumbnails_generated": thumbnails_generated},
            "data": phase_data
        })
        
        return {
            "phase": "thumbnail_generation",
            "success": True,
            "completed": completed,
            "thumbnails_generated": thumbnails_generated
        }


# Global executor registry for managing active runs
_active_executors: Dict[str, PipelineExecutor] = {}
_active_tasks: Dict[str, asyncio.Task] = {}


def get_executor(run_id: str) -> Optional[PipelineExecutor]:
    """Get the executor for a run if it exists."""
    return _active_executors.get(run_id)


def get_task(run_id: str) -> Optional[asyncio.Task]:
    """Get the asyncio Task for a run if it exists."""
    return _active_tasks.get(run_id)


def register_executor(run_id: str, executor: PipelineExecutor, task: asyncio.Task = None):
    """Register an executor and optionally its task for a run."""
    _active_executors[run_id] = executor
    if task:
        _active_tasks[run_id] = task
        executor.set_task(task)


def unregister_executor(run_id: str):
    """Unregister an executor and its task for a run."""
    _active_executors.pop(run_id, None)
    _active_tasks.pop(run_id, None)


async def start_pipeline(run_id: str, mode: PipelineMode, progress_callback: Callable = None) -> Dict[str, Any]:
    """
    Start a pipeline run.
    
    Args:
        run_id: Pipeline run ID
        mode: Execution mode (auto or step)
        progress_callback: Optional callback for progress updates
    
    Returns:
        Execution result
    """
    # Get the run config from the database
    run = get_pipeline_run(run_id)
    run_config = run.get('config', {}) if run else {}
    if isinstance(run_config, str):
        import json
        run_config = json.loads(run_config)
    
    executor = PipelineExecutor(run_id, progress_callback=progress_callback, run_config=run_config)
    
    # Get the current task so we can store it
    current_task = asyncio.current_task()
    register_executor(run_id, executor, current_task)
    
    try:
        if mode == PipelineMode.AUTO:
            result = await executor.run_auto_mode()
        else:
            # Step mode starts in paused state, waiting for phase commands
            update_pipeline_run(run_id, status='paused')
            result = {"success": True, "status": "paused", "message": "Ready for step-by-step execution"}
        
        return result
    except asyncio.CancelledError:
        logger.info(f"Pipeline run {run_id} task was cancelled externally")
        update_pipeline_run(run_id, status='cancelled', completed_at=datetime.utcnow())
        return {"success": False, "status": "cancelled"}
    finally:
        unregister_executor(run_id)


async def run_phase(run_id: str, phase: str, progress_callback: Callable = None) -> Dict[str, Any]:
    """
    Run a specific phase in step mode.
    
    Args:
        run_id: Pipeline run ID
        phase: Phase to execute
        progress_callback: Optional callback for progress updates
    
    Returns:
        Phase execution result
    """
    executor = get_executor(run_id)
    
    if not executor:
        executor = PipelineExecutor(run_id, progress_callback=progress_callback)
        current_task = asyncio.current_task()
        register_executor(run_id, executor, current_task)
    
    try:
        return await executor.run_step_mode_phase(phase)
    except asyncio.CancelledError:
        logger.info(f"Phase {phase} was cancelled for run {run_id}")
        return {"success": False, "status": "cancelled"}
    except Exception as e:
        logger.error(f"Phase {phase} failed: {e}")
        return {"success": False, "error": str(e)}


def cancel_pipeline(run_id: str) -> bool:
    """
    Cancel a running pipeline. Returns True if cancellation was initiated.
    
    This does two things:
    1. Sets the cancelled flag on the executor (graceful stop at next checkpoint)
    2. Cancels the asyncio Task itself (immediate interruption)
    """
    executor = get_executor(run_id)
    if executor:
        executor.cancel()
        return True
    
    # Even without an executor, try to cancel the task
    task = get_task(run_id)
    if task and not task.done():
        task.cancel()
        return True
    
    return False


async def wait_for_cancellation(run_id: str, timeout: float = 10.0) -> bool:
    """
    Wait for a pipeline to fully stop after cancellation.
    
    Returns True if the pipeline stopped within the timeout, False otherwise.
    """
    task = get_task(run_id)
    if not task:
        return True  # No task means nothing to wait for
    
    if task.done():
        return True
    
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        logger.warning(f"Pipeline {run_id} did not stop within {timeout}s timeout")
        return False
    except asyncio.CancelledError:
        return True
    except Exception:
        return True  # Task finished (possibly with error)

