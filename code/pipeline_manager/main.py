"""
Pipeline Manager - FastAPI Application

Unified web UI to orchestrate the entire content pipeline.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import config
from .models import (
    PipelineMode, PipelineStatus, StartPipelineRequest, CancelRunRequest,
    PipelineRunSummary, PipelineRunDetail, PipelineStats, PhaseProgress,
    ActiveRunResponse, CleanupPreview
)
from .db import (
    init_schema, create_pipeline_run, get_pipeline_run, get_active_pipeline_run,
    list_pipeline_runs, update_pipeline_run, get_cleanup_preview,
    cancel_and_cleanup_run, cancel_run_keep_data,
    get_leads_for_run, get_research_for_run, get_generations_for_run,
    get_photos_for_run, get_thumbnails_for_run, get_stories_for_run
)
from .executor import start_pipeline, run_phase, cancel_pipeline, get_executor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# SSE event queues for each run
_event_queues: Dict[str, asyncio.Queue] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Pipeline Manager starting up...")
    try:
        init_schema()
        logger.info("Database schema initialized")
    except Exception as e:
        logger.error(f"Failed to initialize schema: {e}")
    yield
    # Shutdown
    logger.info("Pipeline Manager shutting down...")


app = FastAPI(
    title="Pipeline Manager",
    description="Unified Content Pipeline UI for TheBoldUnknown",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(config.static_dir)), name="static")


# =============================================================================
# Helper Functions
# =============================================================================

def _format_run_summary(run: Dict[str, Any]) -> PipelineRunSummary:
    """Format a database run record into a summary response."""
    stats = run.get('stats', {})
    if isinstance(stats, str):
        stats = json.loads(stats)
    
    return PipelineRunSummary(
        id=str(run['id']),
        mode=PipelineMode(run['mode']),
        status=PipelineStatus(run['status']),
        current_phase=run.get('current_phase'),
        current_phase_index=run.get('current_phase_index', 0),
        total_phases=run.get('total_phases', 5),
        started_at=run.get('started_at'),
        completed_at=run.get('completed_at'),
        created_at=run.get('created_at'),
        stats=PipelineStats(**stats) if stats else PipelineStats()
    )


def _format_run_detail(run: Dict[str, Any]) -> PipelineRunDetail:
    """Format a database run record into a detailed response."""
    stats = run.get('stats', {})
    if isinstance(stats, str):
        stats = json.loads(stats)
    
    phases_data = run.get('phases', [])
    if isinstance(phases_data, str):
        phases_data = json.loads(phases_data)
    
    phases = []
    for p in phases_data:
        phases.append(PhaseProgress(
            phase=p.get('phase', ''),
            status=p.get('status', 'pending'),
            started_at=p.get('started_at'),
            completed_at=p.get('completed_at'),
            total_items=p.get('total_items', 0),
            completed_items=p.get('completed_items', 0),
            error_message=p.get('error_message')
        ))
    
    run_config = run.get('config', {})
    if isinstance(run_config, str):
        run_config = json.loads(run_config)
    
    return PipelineRunDetail(
        id=str(run['id']),
        mode=PipelineMode(run['mode']),
        status=PipelineStatus(run['status']),
        current_phase=run.get('current_phase'),
        current_phase_index=run.get('current_phase_index', 0),
        total_phases=run.get('total_phases', 5),
        started_at=run.get('started_at'),
        completed_at=run.get('completed_at'),
        created_at=run.get('created_at'),
        stats=PipelineStats(**stats) if stats else PipelineStats(),
        phases=phases,
        error_message=run.get('error_message'),
        config=run_config
    )


def _get_or_create_event_queue(run_id: str) -> asyncio.Queue:
    """Get or create an event queue for SSE streaming."""
    if run_id not in _event_queues:
        _event_queues[run_id] = asyncio.Queue()
    return _event_queues[run_id]


def _broadcast_event(run_id: str, event: Dict[str, Any]):
    """Broadcast an event to all SSE listeners for a run."""
    if run_id in _event_queues:
        try:
            _event_queues[run_id].put_nowait(event)
        except asyncio.QueueFull:
            pass  # Drop events if queue is full


# =============================================================================
# Static File Routes
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard."""
    return FileResponse(config.static_dir / "index.html")


@app.get("/pipeline/{run_id}", response_class=HTMLResponse)
async def pipeline_view(run_id: str):
    """Serve the pipeline view for a specific run."""
    return FileResponse(config.static_dir / "pipeline.html")


# =============================================================================
# API Routes - Session & Active Run
# =============================================================================

@app.get("/api/pipeline/active", response_model=ActiveRunResponse)
async def get_active_run():
    """
    Check for any active (running/paused) pipeline run.
    Used by the dashboard to auto-redirect users.
    """
    run = get_active_pipeline_run()
    
    if run:
        return ActiveRunResponse(
            has_active_run=True,
            run=_format_run_summary(run),
            redirect_url=f"/pipeline/{run['id']}"
        )
    
    return ActiveRunResponse(has_active_run=False, run=None, redirect_url=None)


# =============================================================================
# API Routes - Pipeline Management
# =============================================================================

@app.post("/api/pipeline/start")
async def start_new_pipeline(request: StartPipelineRequest, background_tasks: BackgroundTasks):
    """Start a new pipeline run."""
    # Check for existing active run
    active = get_active_pipeline_run()
    if active:
        raise HTTPException(
            status_code=409,
            detail=f"An active pipeline run ({active['id']}) already exists. Cancel it first."
        )
    
    # Create new run
    run_id = create_pipeline_run(request.mode, request.config)
    
    # Progress callback for SSE
    def progress_callback(event: Dict[str, Any]):
        _broadcast_event(run_id, event)
    
    # Start execution in background
    background_tasks.add_task(start_pipeline, run_id, request.mode, progress_callback)
    
    # Return immediately with run details
    run = get_pipeline_run(run_id)
    return {
        "success": True,
        "run_id": run_id,
        "run": _format_run_summary(run)
    }


@app.get("/api/pipeline/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None)
):
    """List pipeline runs with pagination."""
    runs = list_pipeline_runs(limit=limit, offset=offset, status=status)
    return {
        "runs": [_format_run_summary(r) for r in runs],
        "limit": limit,
        "offset": offset
    }


@app.get("/api/pipeline/runs/{run_id}")
async def get_run_details(run_id: str):
    """Get full details of a pipeline run."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    return _format_run_detail(run)


@app.post("/api/pipeline/runs/{run_id}/pause")
async def pause_run(run_id: str):
    """Pause a running pipeline."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    if run['status'] != 'running':
        raise HTTPException(status_code=400, detail="Can only pause running pipelines")
    
    executor = get_executor(run_id)
    if executor:
        executor.pause()
    
    update_pipeline_run(run_id, status='paused')
    
    return {"success": True, "status": "paused"}


@app.post("/api/pipeline/runs/{run_id}/resume")
async def resume_run(run_id: str, background_tasks: BackgroundTasks):
    """Resume a paused pipeline."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    if run['status'] != 'paused':
        raise HTTPException(status_code=400, detail="Can only resume paused pipelines")
    
    executor = get_executor(run_id)
    if executor:
        executor.resume()
    
    # For auto mode, restart execution
    if run['mode'] == 'auto':
        def progress_callback(event: Dict[str, Any]):
            _broadcast_event(run_id, event)
        
        background_tasks.add_task(start_pipeline, run_id, PipelineMode.AUTO, progress_callback)
    
    return {"success": True, "status": "running"}


@app.post("/api/pipeline/runs/{run_id}/cancel")
async def cancel_run(run_id: str, delete_data: bool = Query(True)):
    """Cancel a pipeline run, optionally deleting all created data."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    # Signal cancellation to executor
    cancel_pipeline(run_id)
    
    if delete_data:
        result = cancel_and_cleanup_run(run_id)
    else:
        result = cancel_run_keep_data(run_id)
    
    _broadcast_event(run_id, {"event": "pipeline_cancelled", "run_id": run_id})
    
    return result


@app.get("/api/pipeline/runs/{run_id}/cleanup-preview")
async def preview_cleanup(run_id: str):
    """Get counts of records that would be deleted on cancellation."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    preview = get_cleanup_preview(run_id)
    return preview


@app.delete("/api/pipeline/runs/{run_id}")
async def delete_run(run_id: str):
    """Delete a completed/cancelled run from history."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    if run['status'] in ('running', 'paused'):
        raise HTTPException(status_code=400, detail="Cannot delete active pipeline runs")
    
    # Delete the run and all associated data
    result = cancel_and_cleanup_run(run_id)
    return result


# =============================================================================
# API Routes - Phase Control (Step Mode)
# =============================================================================

@app.post("/api/pipeline/runs/{run_id}/phase/{phase}/start")
async def start_phase(run_id: str, phase: str, background_tasks: BackgroundTasks):
    """Start a specific phase in step mode."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    if run['mode'] != 'step':
        raise HTTPException(status_code=400, detail="Phase control only available in step mode")
    
    if run['status'] not in ('paused', 'pending'):
        raise HTTPException(status_code=400, detail="Pipeline must be paused to start a phase")
    
    def progress_callback(event: Dict[str, Any]):
        _broadcast_event(run_id, event)
    
    background_tasks.add_task(run_phase, run_id, phase, progress_callback)
    
    return {"success": True, "message": f"Started phase: {phase}"}


@app.post("/api/pipeline/runs/{run_id}/phase/{phase}/retry")
async def retry_phase(run_id: str, phase: str, background_tasks: BackgroundTasks):
    """Retry a failed phase."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    def progress_callback(event: Dict[str, Any]):
        _broadcast_event(run_id, event)
    
    background_tasks.add_task(run_phase, run_id, phase, progress_callback)
    
    return {"success": True, "message": f"Retrying phase: {phase}"}


@app.post("/api/pipeline/runs/{run_id}/phase/{phase}/skip")
async def skip_phase(run_id: str, phase: str):
    """Skip a phase (mark as skipped and continue)."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    from .db import update_phase_status
    update_phase_status(run_id, phase, 'skipped')
    
    return {"success": True, "message": f"Skipped phase: {phase}"}


@app.post("/api/pipeline/runs/{run_id}/phase/{phase}/approve")
async def approve_phase(run_id: str, phase: str):
    """Approve phase results in step mode."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    # Simply acknowledge approval - the next phase can be started
    return {"success": True, "message": f"Phase {phase} approved"}


# =============================================================================
# API Routes - Real-time Updates (SSE)
# =============================================================================

@app.get("/api/pipeline/runs/{run_id}/stream")
async def stream_progress(run_id: str, request: Request):
    """SSE stream for real-time progress updates."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    async def event_generator():
        queue = _get_or_create_event_queue(run_id)
        
        # Send initial state
        run_data = get_pipeline_run(run_id)
        if run_data:
            yield f"event: state\ndata: {json.dumps(_format_run_detail(run_data).model_dump(mode='json'))}\n\n"
        
        # Listen for updates
        while True:
            if await request.is_disconnected():
                break
            
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"event: {event.get('event', 'update')}\ndata: {json.dumps(event)}\n\n"
                
                # Check if pipeline is done
                if event.get('event') in ('pipeline_complete', 'pipeline_cancelled', 'pipeline_error'):
                    break
                    
            except asyncio.TimeoutError:
                # Send heartbeat
                yield f"event: heartbeat\ndata: {json.dumps({'time': datetime.utcnow().isoformat()})}\n\n"
            
            # Check run status
            current_run = get_pipeline_run(run_id)
            if current_run and current_run.get('status') in ('completed', 'cancelled', 'failed'):
                yield f"event: done\ndata: {json.dumps({'status': current_run.get('status')})}\n\n"
                break
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# =============================================================================
# API Routes - Phase Results
# =============================================================================

@app.get("/api/pipeline/runs/{run_id}/phases")
async def get_phases_summary(run_id: str):
    """Get summary of all phases for a run."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    return _format_run_detail(run).phases


@app.get("/api/pipeline/runs/{run_id}/phases/1/leads")
async def get_lead_results(run_id: str):
    """Get Phase 1 (Lead Generation) results."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    leads = get_leads_for_run(run_id)
    return {
        "phase": "lead_generation",
        "total": len(leads),
        "leads": leads
    }


@app.get("/api/pipeline/runs/{run_id}/phases/2/research")
async def get_research_results(run_id: str):
    """Get Phase 2 (Story Research) results."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    research = get_research_for_run(run_id)
    return {
        "phase": "story_research",
        "total": len(research),
        "research": research
    }


@app.get("/api/pipeline/runs/{run_id}/phases/3/text")
async def get_text_results(run_id: str):
    """Get Phase 3 (Text Generation) results."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    generations = get_generations_for_run(run_id)
    return {
        "phase": "text_generation",
        "total": len(generations),
        "generations": generations
    }


@app.get("/api/pipeline/runs/{run_id}/phases/4/photos")
async def get_photo_results(run_id: str):
    """Get Phase 4 (Photo Research) results."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    photos = get_photos_for_run(run_id)
    approved = [p for p in photos if p.get('status') == 'approved']
    rejected = [p for p in photos if p.get('status') == 'rejected']
    
    return {
        "phase": "photo_research",
        "total": len(photos),
        "approved": len(approved),
        "rejected": len(rejected),
        "photos": photos
    }


@app.get("/api/pipeline/runs/{run_id}/phases/5/thumbnails")
async def get_thumbnail_results(run_id: str):
    """Get Phase 5 (Thumbnail Generation) results."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    thumbnails = get_thumbnails_for_run(run_id)
    return {
        "phase": "thumbnail_generation",
        "total": len(thumbnails),
        "thumbnails": thumbnails
    }


@app.get("/api/pipeline/runs/{run_id}/stories")
async def get_stories_status(run_id: str):
    """Get all story statuses for a run."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    stories = get_stories_for_run(run_id)
    return {
        "total": len(stories),
        "stories": stories
    }


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "pipeline-manager"}


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.debug
    )

