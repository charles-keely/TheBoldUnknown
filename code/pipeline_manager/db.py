"""
Database operations for Pipeline Manager.
"""

import os
import uuid
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from .config import config
from .models import (
    PipelineStatus, PhaseStatus, PipelineMode,
    PipelineRunSummary, PipelineRunDetail, PipelineStats, PhaseProgress,
    LeadResult, ResearchResult, TextGenerationResult, PhotoResult, ThumbnailResult,
    CleanupPreview, StoryStatusInPipeline
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(config.base_dir.parent / '.env')


def get_db_connection():
    """Establishes and returns a database connection."""
    try:
        db_url = os.getenv("DATABASE_URL") or config.database_url
        connect_timeout = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))
        statement_timeout_ms = int(os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS", "30000"))
        
        conn = psycopg.connect(
            db_url,
            connect_timeout=connect_timeout,
            options=f"-c statement_timeout={statement_timeout_ms}",
            row_factory=dict_row,
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


@contextmanager
def get_db_cursor():
    """Context manager for database cursor with automatic cleanup."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            yield cur
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


# =============================================================================
# Schema Initialization
# =============================================================================

def init_schema():
    """Initialize the pipeline manager database schema."""
    schema_sql = """
    -- Pipeline run tracking
    CREATE TABLE IF NOT EXISTS public.pipeline_runs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        mode TEXT NOT NULL CHECK (mode IN ('auto', 'step')),
        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')),
        current_phase TEXT,
        current_phase_index INTEGER DEFAULT 0,
        total_phases INTEGER DEFAULT 5,
        started_at TIMESTAMP WITH TIME ZONE,
        completed_at TIMESTAMP WITH TIME ZONE,
        error_message TEXT,
        config JSONB DEFAULT '{}',
        stats JSONB DEFAULT '{"leads_discovered": 0, "leads_approved": 0, "research_completed": 0, "generations_completed": 0, "photos_found": 0, "photos_approved": 0, "thumbnails_generated": 0}',
        phases JSONB DEFAULT '[]',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
    );

    -- Per-story progress within a pipeline run
    CREATE TABLE IF NOT EXISTS public.pipeline_story_status (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE CASCADE,
        lead_id UUID,
        story_research_id UUID,
        story_generation_id UUID,
        title TEXT,
        phase_statuses JSONB DEFAULT '{}',
        error_log JSONB DEFAULT '[]',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
    );

    -- Index for finding active runs quickly
    CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status) WHERE status IN ('running', 'paused');
    CREATE INDEX IF NOT EXISTS idx_pipeline_story_status_run ON pipeline_story_status(pipeline_run_id);

    -- Add pipeline_run_id to existing tables if not exists
    DO $$ 
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'pipeline_run_id') THEN
            ALTER TABLE leads ADD COLUMN pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'story_research' AND column_name = 'pipeline_run_id') THEN
            ALTER TABLE story_research ADD COLUMN pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'story_generations' AND column_name = 'pipeline_run_id') THEN
            ALTER TABLE story_generations ADD COLUMN pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'story_photos' AND column_name = 'pipeline_run_id') THEN
            ALTER TABLE story_photos ADD COLUMN pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'story_thumbnails' AND column_name = 'pipeline_run_id') THEN
            ALTER TABLE story_thumbnails ADD COLUMN pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
        END IF;
    END $$;

    -- Create indexes for cleanup queries if not exist
    CREATE INDEX IF NOT EXISTS idx_leads_pipeline_run ON leads(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_story_research_pipeline_run ON story_research(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_story_generations_pipeline_run ON story_generations(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_story_photos_pipeline_run ON story_photos(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_story_thumbnails_pipeline_run ON story_thumbnails(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
    """
    
    with get_db_cursor() as cur:
        cur.execute(schema_sql)
    logger.info("Pipeline manager schema initialized")


# =============================================================================
# Pipeline Run Operations
# =============================================================================

def create_pipeline_run(mode: PipelineMode, run_config: Dict[str, Any] = None) -> str:
    """Create a new pipeline run and return its ID."""
    run_id = str(uuid.uuid4())
    initial_phases = [
        {"phase": "lead_generation", "status": "pending", "order": 1},
        {"phase": "story_research", "status": "pending", "order": 2},
        {"phase": "text_generation", "status": "pending", "order": 3},
        {"phase": "photo_research", "status": "pending", "order": 4},
        {"phase": "thumbnail_generation", "status": "pending", "order": 5},
    ]
    
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO pipeline_runs (id, mode, status, config, phases, current_phase_index, total_phases)
            VALUES (%s, %s, 'pending', %s, %s, 0, 5)
            RETURNING id
        """, (run_id, mode.value, json.dumps(run_config or {}), json.dumps(initial_phases)))
        result = cur.fetchone()
        return str(result['id'])


def get_pipeline_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Get a pipeline run by ID."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT * FROM pipeline_runs WHERE id = %s
        """, (run_id,))
        return cur.fetchone()


def get_active_pipeline_run() -> Optional[Dict[str, Any]]:
    """Get the currently active (running or paused) pipeline run."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT * FROM pipeline_runs 
            WHERE status IN ('running', 'paused')
            ORDER BY created_at DESC
            LIMIT 1
        """)
        return cur.fetchone()


def list_pipeline_runs(limit: int = 20, offset: int = 0, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List pipeline runs with pagination."""
    with get_db_cursor() as cur:
        if status:
            cur.execute("""
                SELECT * FROM pipeline_runs
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (status, limit, offset))
        else:
            cur.execute("""
                SELECT * FROM pipeline_runs
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
        return cur.fetchall()


def update_pipeline_run(run_id: str, **kwargs) -> bool:
    """Update pipeline run fields."""
    if not kwargs:
        return False
    
    # Build dynamic update query
    set_clauses = []
    values = []
    for key, value in kwargs.items():
        if key in ('status', 'current_phase', 'current_phase_index', 'error_message', 'stats', 'phases', 'started_at', 'completed_at'):
            set_clauses.append(f"{key} = %s")
            if key in ('stats', 'phases'):
                values.append(json.dumps(value) if isinstance(value, (dict, list)) else value)
            else:
                values.append(value)
    
    if not set_clauses:
        return False
    
    set_clauses.append("updated_at = now()")
    values.append(run_id)
    
    with get_db_cursor() as cur:
        cur.execute(f"""
            UPDATE pipeline_runs
            SET {', '.join(set_clauses)}
            WHERE id = %s
        """, values)
        return cur.rowcount > 0


def update_pipeline_stats(run_id: str, stats: Dict[str, int]) -> bool:
    """Update pipeline run statistics."""
    with get_db_cursor() as cur:
        cur.execute("""
            UPDATE pipeline_runs
            SET stats = stats || %s::jsonb, updated_at = now()
            WHERE id = %s
        """, (json.dumps(stats), run_id))
        return cur.rowcount > 0


def update_phase_status(run_id: str, phase: str, status: str, **kwargs) -> bool:
    """Update a specific phase's status in the pipeline run."""
    run = get_pipeline_run(run_id)
    if not run:
        return False
    
    phases = run.get('phases', [])
    if isinstance(phases, str):
        phases = json.loads(phases)
    
    for p in phases:
        if p['phase'] == phase:
            p['status'] = status
            if 'started_at' in kwargs:
                p['started_at'] = kwargs['started_at'].isoformat() if kwargs['started_at'] else None
            if 'completed_at' in kwargs:
                p['completed_at'] = kwargs['completed_at'].isoformat() if kwargs['completed_at'] else None
            if 'total_items' in kwargs:
                p['total_items'] = kwargs['total_items']
            if 'completed_items' in kwargs:
                p['completed_items'] = kwargs['completed_items']
            if 'error_message' in kwargs:
                p['error_message'] = kwargs['error_message']
            break
    
    return update_pipeline_run(run_id, phases=phases)


# =============================================================================
# Story Status Operations
# =============================================================================

def create_story_status(run_id: str, lead_id: str, title: str) -> str:
    """Create a story status entry for a pipeline run."""
    status_id = str(uuid.uuid4())
    initial_statuses = {
        "lead_generation": "completed",
        "curation": "pending",
        "story_research": "pending",
        "text_generation": "pending",
        "photo_research": "pending",
        "thumbnail_generation": "pending",
    }
    
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO pipeline_story_status (id, pipeline_run_id, lead_id, title, phase_statuses)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (status_id, run_id, lead_id, title, json.dumps(initial_statuses)))
        return status_id


def update_story_status(status_id: str, phase: str, status: str, **kwargs) -> bool:
    """Update a story's phase status."""
    with get_db_cursor() as cur:
        # Get current statuses
        cur.execute("SELECT phase_statuses FROM pipeline_story_status WHERE id = %s", (status_id,))
        row = cur.fetchone()
        if not row:
            return False
        
        phase_statuses = row['phase_statuses']
        if isinstance(phase_statuses, str):
            phase_statuses = json.loads(phase_statuses)
        
        phase_statuses[phase] = status
        
        # Update with any additional fields
        update_fields = ["phase_statuses = %s", "updated_at = now()"]
        values = [json.dumps(phase_statuses)]
        
        if 'story_research_id' in kwargs:
            update_fields.append("story_research_id = %s")
            values.append(kwargs['story_research_id'])
        if 'story_generation_id' in kwargs:
            update_fields.append("story_generation_id = %s")
            values.append(kwargs['story_generation_id'])
        
        values.append(status_id)
        
        cur.execute(f"""
            UPDATE pipeline_story_status
            SET {', '.join(update_fields)}
            WHERE id = %s
        """, values)
        return cur.rowcount > 0


def get_stories_for_run(run_id: str) -> List[Dict[str, Any]]:
    """Get all story statuses for a pipeline run."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT * FROM pipeline_story_status
            WHERE pipeline_run_id = %s
            ORDER BY created_at ASC
        """, (run_id,))
        return cur.fetchall()


def link_lead_to_run(lead_id: str, run_id: str) -> bool:
    """Link a lead to a pipeline run."""
    with get_db_cursor() as cur:
        cur.execute("""
            UPDATE leads SET pipeline_run_id = %s WHERE id = %s
        """, (run_id, lead_id))
        return cur.rowcount > 0


def link_research_to_run(research_id: str, run_id: str) -> bool:
    """Link a story_research to a pipeline run."""
    with get_db_cursor() as cur:
        cur.execute("""
            UPDATE story_research SET pipeline_run_id = %s WHERE id = %s
        """, (run_id, research_id))
        return cur.rowcount > 0


def link_generation_to_run(generation_id: str, run_id: str) -> bool:
    """Link a story_generation to a pipeline run."""
    with get_db_cursor() as cur:
        cur.execute("""
            UPDATE story_generations SET pipeline_run_id = %s WHERE id = %s
        """, (run_id, generation_id))
        return cur.rowcount > 0


# =============================================================================
# Phase Result Queries
# =============================================================================

def get_leads_for_run(run_id: str) -> List[Dict[str, Any]]:
    """Get all leads created in a pipeline run."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT l.*, 
                   COALESCE(
                       (SELECT notes FROM story_research sr WHERE sr.lead_id = l.id LIMIT 1),
                       ''
                   ) as curator_reasoning
            FROM leads l
            WHERE l.pipeline_run_id = %s
            ORDER BY l.created_at ASC
        """, (run_id,))
        return cur.fetchall()


def get_research_for_run(run_id: str) -> List[Dict[str, Any]]:
    """Get all story research for a pipeline run."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT sr.*, l.title, l.url
            FROM story_research sr
            JOIN leads l ON sr.lead_id = l.id
            WHERE sr.pipeline_run_id = %s
            ORDER BY sr.created_at ASC
        """, (run_id,))
        return cur.fetchall()


def get_generations_for_run(run_id: str) -> List[Dict[str, Any]]:
    """Get all story generations for a pipeline run."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT sg.*, 
                   l.title as lead_title,
                   (SELECT COUNT(*) FROM story_slides ss WHERE ss.story_generation_id = sg.id) as slide_count,
                   (SELECT SUM(LENGTH(text_content)) FROM story_slides ss WHERE ss.story_generation_id = sg.id) as char_count
            FROM story_generations sg
            JOIN story_research sr ON sg.story_research_id = sr.id
            JOIN leads l ON sr.lead_id = l.id
            WHERE sg.pipeline_run_id = %s
            ORDER BY sg.created_at ASC
        """, (run_id,))
        return cur.fetchall()


def get_photos_for_run(run_id: str) -> List[Dict[str, Any]]:
    """Get all photos for a pipeline run."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT sp.*, l.title as story_title
            FROM story_photos sp
            JOIN story_research sr ON sp.story_research_id = sr.id
            JOIN leads l ON sr.lead_id = l.id
            WHERE sp.pipeline_run_id = %s
            ORDER BY sp.created_at ASC
        """, (run_id,))
        return cur.fetchall()


def get_thumbnails_for_run(run_id: str) -> List[Dict[str, Any]]:
    """Get all thumbnails for a pipeline run."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT st.*, sg.hook_title as story_title
            FROM story_thumbnails st
            JOIN story_generations sg ON st.story_generation_id = sg.id
            WHERE st.pipeline_run_id = %s
            ORDER BY st.created_at ASC
        """, (run_id,))
        return cur.fetchall()


# =============================================================================
# Cleanup Operations
# =============================================================================

def get_cleanup_preview(run_id: str) -> CleanupPreview:
    """Get counts of records that would be deleted on cancellation."""
    with get_db_cursor() as cur:
        preview = CleanupPreview()
        
        cur.execute("SELECT COUNT(*) as cnt FROM leads WHERE pipeline_run_id = %s", (run_id,))
        preview.leads = cur.fetchone()['cnt']
        
        cur.execute("SELECT COUNT(*) as cnt FROM story_research WHERE pipeline_run_id = %s", (run_id,))
        preview.research = cur.fetchone()['cnt']
        
        cur.execute("SELECT COUNT(*) as cnt FROM story_generations WHERE pipeline_run_id = %s", (run_id,))
        preview.generations = cur.fetchone()['cnt']
        
        cur.execute("""
            SELECT COUNT(*) as cnt FROM story_slides 
            WHERE story_generation_id IN (SELECT id FROM story_generations WHERE pipeline_run_id = %s)
        """, (run_id,))
        preview.slides = cur.fetchone()['cnt']
        
        cur.execute("SELECT COUNT(*) as cnt FROM story_photos WHERE pipeline_run_id = %s", (run_id,))
        preview.photos = cur.fetchone()['cnt']
        
        cur.execute("SELECT COUNT(*) as cnt FROM story_thumbnails WHERE pipeline_run_id = %s", (run_id,))
        preview.thumbnails = cur.fetchone()['cnt']
        
        return preview


def cancel_and_cleanup_run(run_id: str) -> Dict[str, Any]:
    """Cancel a pipeline run and delete all data created during it."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            
            # Delete in reverse dependency order
            
            # Thumbnails
            cur.execute("""
                DELETE FROM story_thumbnails WHERE pipeline_run_id = %s RETURNING id
            """, (run_id,))
            thumbnails_deleted = len(cur.fetchall())
            
            # Slides (via generation)
            cur.execute("""
                DELETE FROM story_slides 
                WHERE story_generation_id IN (
                    SELECT id FROM story_generations WHERE pipeline_run_id = %s
                )
                RETURNING id
            """, (run_id,))
            slides_deleted = len(cur.fetchall())
            
            # Photos
            cur.execute("""
                DELETE FROM story_photos WHERE pipeline_run_id = %s RETURNING id
            """, (run_id,))
            photos_deleted = len(cur.fetchall())
            
            # Story generations
            cur.execute("""
                DELETE FROM story_generations WHERE pipeline_run_id = %s RETURNING id
            """, (run_id,))
            generations_deleted = len(cur.fetchall())
            
            # Story research
            cur.execute("""
                DELETE FROM story_research WHERE pipeline_run_id = %s RETURNING id
            """, (run_id,))
            research_deleted = len(cur.fetchall())
            
            # Leads
            cur.execute("""
                DELETE FROM leads WHERE pipeline_run_id = %s RETURNING id
            """, (run_id,))
            leads_deleted = len(cur.fetchall())
            
            # Pipeline story statuses
            cur.execute("""
                DELETE FROM pipeline_story_status WHERE pipeline_run_id = %s
            """, (run_id,))
            
            # Update run status
            cur.execute("""
                UPDATE pipeline_runs 
                SET status = 'cancelled', completed_at = now(), updated_at = now()
                WHERE id = %s
            """, (run_id,))
            
            conn.commit()
            
            return {
                "success": True,
                "deleted": {
                    "leads": leads_deleted,
                    "research": research_deleted,
                    "generations": generations_deleted,
                    "slides": slides_deleted,
                    "photos": photos_deleted,
                    "thumbnails": thumbnails_deleted
                }
            }
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def cancel_run_keep_data(run_id: str) -> Dict[str, Any]:
    """Cancel a pipeline run but keep all created data."""
    with get_db_cursor() as cur:
        cur.execute("""
            UPDATE pipeline_runs 
            SET status = 'cancelled', completed_at = now(), updated_at = now()
            WHERE id = %s
        """, (run_id,))
        return {"success": True, "deleted": {}}


# =============================================================================
# Helper Queries for Workers
# =============================================================================

def get_pending_leads_for_curation() -> List[Dict[str, Any]]:
    """Get leads pending curation."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT * FROM leads 
            WHERE status = 'new'
            ORDER BY virality_score DESC, brand_score DESC
            LIMIT 100
        """)
        return cur.fetchall()


def get_curated_leads_for_research(run_id: str) -> List[Dict[str, Any]]:
    """Get curated/approved leads ready for research."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT l.* FROM leads l
            WHERE l.pipeline_run_id = %s
            AND l.status = 'approved'
            AND NOT EXISTS (
                SELECT 1 FROM story_research sr WHERE sr.lead_id = l.id
            )
            ORDER BY l.created_at ASC
        """, (run_id,))
        return cur.fetchall()


def get_researched_stories_for_text_gen(run_id: str) -> List[Dict[str, Any]]:
    """Get researched stories ready for text generation."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT sr.*, l.title, l.url, l.summary
            FROM story_research sr
            JOIN leads l ON sr.lead_id = l.id
            WHERE sr.pipeline_run_id = %s
            AND sr.status = 'completed'
            AND NOT EXISTS (
                SELECT 1 FROM story_generations sg WHERE sg.story_research_id = sr.id
            )
            ORDER BY sr.created_at ASC
        """, (run_id,))
        return cur.fetchall()


def get_stories_needing_photos(run_id: str) -> List[Dict[str, Any]]:
    """Get stories ready for photo research."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT sg.*, sr.research_data, l.title, l.url
            FROM story_generations sg
            JOIN story_research sr ON sg.story_research_id = sr.id
            JOIN leads l ON sr.lead_id = l.id
            WHERE sg.pipeline_run_id = %s
            AND NOT EXISTS (
                SELECT 1 FROM story_photos sp 
                WHERE sp.story_research_id = sr.id AND sp.status = 'approved'
            )
            ORDER BY sg.created_at ASC
        """, (run_id,))
        return cur.fetchall()


def get_stories_needing_thumbnails(run_id: str) -> List[Dict[str, Any]]:
    """Get stories ready for thumbnail generation."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT sg.*, sr.research_data
            FROM story_generations sg
            JOIN story_research sr ON sg.story_research_id = sr.id
            WHERE sg.pipeline_run_id = %s
            AND NOT EXISTS (
                SELECT 1 FROM story_thumbnails st 
                WHERE st.story_generation_id = sg.id AND st.status = 'generated'
            )
            ORDER BY sg.created_at ASC
        """, (run_id,))
        return cur.fetchall()

