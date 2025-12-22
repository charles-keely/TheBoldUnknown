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
    """Get all story generations for a pipeline run.
    
    Includes research_data and slides so downstream workers (photo_researcher)
    have the context needed to generate relevant queries.
    """
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT sg.*, 
                   l.title as lead_title,
                   sr.research_data,
                   (SELECT COUNT(*) FROM story_slides ss WHERE ss.story_generation_id = sg.id) as slide_count,
                   (SELECT SUM(LENGTH(text_content)) FROM story_slides ss WHERE ss.story_generation_id = sg.id) as char_count,
                   (SELECT json_agg(
                       json_build_object(
                           'id', ss.id,
                           'slide_order', ss.slide_order,
                           'text_content', ss.text_content
                       ) ORDER BY ss.slide_order
                   ) FROM story_slides ss WHERE ss.story_generation_id = sg.id) as slides
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
# Enhanced Phase Data Queries (for visualization)
# =============================================================================

def get_phase1_data(run_id: str) -> Dict[str, Any]:
    """Get comprehensive Phase 1 (Lead Generation) data for visualization."""
    with get_db_cursor() as cur:
        # Get all leads for this run with curator reasoning
        cur.execute("""
            SELECT 
                l.id, l.title, l.url, l.summary,
                l.brand_score, l.virality_score, l.interestingness_score,
                l.viral_hook, l.status, l.source_origin,
                l.substance_analysis, l.created_at,
                sr.notes as curator_reasoning,
                COALESCE(sg.domain_tag, 'UNKNOWN') as domain_tag
            FROM leads l
            LEFT JOIN story_research sr ON sr.lead_id = l.id
            LEFT JOIN story_generations sg ON sg.story_research_id = sr.id
            WHERE l.pipeline_run_id = %s
            ORDER BY l.virality_score DESC NULLS LAST
        """, (run_id,))
        leads = cur.fetchall()
        
        # Calculate statistics
        total = len(leads)
        approved = len([l for l in leads if l.get('status') == 'approved'])
        
        # Calculate score distributions
        virality_scores = [l['virality_score'] for l in leads if l.get('virality_score')]
        brand_scores = [l['brand_score'] for l in leads if l.get('brand_score')]
        
        # Source breakdown
        rss_count = len([l for l in leads if l.get('source_origin', '').startswith('RSS')])
        perplexity_count = len([l for l in leads if 'perplexity' in (l.get('source_origin', '') or '').lower()])
        
        # Get funnel data from pipeline_runs.phases if available
        run = get_pipeline_run(run_id)
        phases = run.get('phases', []) if run else []
        if isinstance(phases, str):
            phases = json.loads(phases)
        
        funnel_data = {}
        for p in phases:
            if p.get('phase') == 'lead_generation' and 'funnel_data' in p:
                funnel_data = p['funnel_data']
                break
        
        return {
            "phase": "lead_generation",
            "total_leads": total,
            "approved_leads": approved,
            "funnel": funnel_data,
            "score_distributions": {
                "virality": {
                    "min": min(virality_scores) if virality_scores else 0,
                    "max": max(virality_scores) if virality_scores else 0,
                    "mean": sum(virality_scores) / len(virality_scores) if virality_scores else 0,
                    "scores": virality_scores
                },
                "brand": {
                    "min": min(brand_scores) if brand_scores else 0,
                    "max": max(brand_scores) if brand_scores else 0,
                    "mean": sum(brand_scores) / len(brand_scores) if brand_scores else 0,
                    "scores": brand_scores
                }
            },
            "source_breakdown": {
                "rss": rss_count,
                "perplexity": perplexity_count,
                "other": total - rss_count - perplexity_count
            },
            "leads": leads
        }


def get_phase2_data(run_id: str) -> Dict[str, Any]:
    """Get comprehensive Phase 2 (Story Research) data for visualization."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT 
                sr.id, sr.status, sr.started_at, sr.completed_at,
                sr.research_data, sr.primary_sources, sr.primary_source_urls,
                sr.notes,
                l.id as lead_id, l.title, l.url, l.summary
            FROM story_research sr
            JOIN leads l ON sr.lead_id = l.id
            WHERE sr.pipeline_run_id = %s
            ORDER BY sr.created_at ASC
        """, (run_id,))
        research_items = cur.fetchall()
        
        # Process research items
        processed_items = []
        total_ground_truth_chars = 0
        total_research_time = 0
        
        for item in research_items:
            research_data = item.get('research_data', {})
            if isinstance(research_data, str):
                research_data = json.loads(research_data) if research_data else {}
            
            ground_truth = research_data.get('ground_truth', '')
            ground_truth_chars = len(ground_truth) if ground_truth else 0
            total_ground_truth_chars += ground_truth_chars
            
            # Calculate research time
            research_time = 0
            if item.get('started_at') and item.get('completed_at'):
                started = item['started_at']
                completed = item['completed_at']
                if hasattr(started, 'timestamp') and hasattr(completed, 'timestamp'):
                    research_time = int((completed.timestamp() - started.timestamp()))
                total_research_time += research_time
            
            # Extract hook from follow_up
            hook = None
            if research_data.get('follow_up'):
                hook = {
                    "question": research_data['follow_up'].get('question'),
                    "answer": research_data['follow_up'].get('answer')
                }
            
            processed_items.append({
                "id": str(item['id']),
                "lead_id": str(item['lead_id']),
                "title": item['title'],
                "url": item['url'],
                "status": item['status'],
                "started_at": item['started_at'].isoformat() if item.get('started_at') else None,
                "completed_at": item['completed_at'].isoformat() if item.get('completed_at') else None,
                "ground_truth": ground_truth,
                "ground_truth_char_count": ground_truth_chars,
                "hook": hook,
                "primary_sources": item.get('primary_sources', []),
                "primary_source_urls": item.get('primary_source_urls', []),
                "research_time_seconds": research_time
            })
        
        completed_count = len([r for r in processed_items if r['status'] == 'completed'])
        in_progress_count = len([r for r in processed_items if r['status'] == 'in_progress'])
        queued_count = len([r for r in processed_items if r['status'] == 'queued'])
        
        return {
            "phase": "story_research",
            "summary": {
                "total": len(processed_items),
                "completed": completed_count,
                "in_progress": in_progress_count,
                "queued": queued_count,
                "failed": len(processed_items) - completed_count - in_progress_count - queued_count
            },
            "total_ground_truth_chars": total_ground_truth_chars,
            "average_research_time_seconds": total_research_time // completed_count if completed_count else 0,
            "research": processed_items
        }


def get_phase3_data(run_id: str) -> Dict[str, Any]:
    """Get comprehensive Phase 3 (Text Generation) data for visualization."""
    with get_db_cursor() as cur:
        # Get generations with slide stats
        cur.execute("""
            SELECT 
                sg.id, sg.story_research_id, sg.hook_title, sg.subtitle, sg.domain_tag,
                sg.instagram_caption, sg.hashtags, sg.generation_metadata, sg.created_at,
                l.title as lead_title,
                sr.id as research_id
            FROM story_generations sg
            JOIN story_research sr ON sg.story_research_id = sr.id
            JOIN leads l ON sr.lead_id = l.id
            WHERE sg.pipeline_run_id = %s
            ORDER BY sg.created_at ASC
        """, (run_id,))
        generations = cur.fetchall()
        
        processed_generations = []
        total_slides = 0
        total_chars = 0
        
        for gen in generations:
            gen_id = gen['id']
            
            # Get slides for this generation
            cur.execute("""
                SELECT 
                    id, slide_order, text_content, document_type_tag, paragraph_count
                FROM story_slides
                WHERE story_generation_id = %s
                ORDER BY slide_order
            """, (str(gen_id),))
            slides = cur.fetchall()
            
            # Calculate slide stats
            slide_count = len(slides)
            char_count = sum(len(s.get('text_content', '')) for s in slides)
            total_slides += slide_count
            total_chars += char_count
            
            # Process slides
            processed_slides = [{
                "order": s['slide_order'],
                "tag": s['document_type_tag'],
                "paragraph_count": s['paragraph_count'] or 1,
                "text": s['text_content'],
                "char_count": len(s.get('text_content', ''))
            } for s in slides]
            
            # Parse generation metadata for cover options
            metadata = gen.get('generation_metadata', {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata) if metadata else {}
            
            cover_options = metadata.get('options', [])
            selected_option = metadata.get('selected_id', 1)
            
            processed_generations.append({
                "id": str(gen['id']),
                "story_research_id": str(gen['story_research_id']),
                "lead_title": gen['lead_title'],
                "hook_title": gen['hook_title'],
                "subtitle": gen['subtitle'],
                "domain_tag": gen['domain_tag'],
                "cover": {
                    "selected_option": selected_option,
                    "options": cover_options
                },
                "slides": processed_slides,
                "total_slides": slide_count,
                "total_characters": char_count,
                "caption": gen['instagram_caption'],
                "caption_char_count": len(gen.get('instagram_caption', '') or ''),
                "hashtags": gen['hashtags'] or []
            })
        
        return {
            "phase": "text_generation",
            "summary": {
                "total": len(processed_generations),
                "completed": len(processed_generations),
                "total_slides": total_slides,
                "total_characters": total_chars,
                "average_slides_per_story": total_slides // len(processed_generations) if processed_generations else 0,
                "average_chars_per_story": total_chars // len(processed_generations) if processed_generations else 0
            },
            "generations": processed_generations
        }


def get_phase4_data(run_id: str) -> Dict[str, Any]:
    """Get comprehensive Phase 4 (Photo Research) data for visualization."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT 
                sp.id, sp.image_url, sp.source_page_url, sp.search_query,
                sp.description, sp.caption, sp.source_attribution, sp.concept_tag,
                sp.relevance_score, sp.verifiability_score, sp.status,
                sp.metadata, sp.created_at,
                sr.id as story_research_id,
                l.title as story_title
            FROM story_photos sp
            JOIN story_research sr ON sp.story_research_id = sr.id
            JOIN leads l ON sr.lead_id = l.id
            WHERE sp.pipeline_run_id = %s
            ORDER BY sr.id, sp.created_at ASC
        """, (run_id,))
        photos = cur.fetchall()
        
        # Calculate overall stats
        total = len(photos)
        approved = len([p for p in photos if p.get('status') == 'approved'])
        rejected = len([p for p in photos if p.get('status') == 'rejected'])
        
        # Count AI-detected
        ai_detected = 0
        rejection_reasons = {"low_relevance": 0, "ai_generated": 0, "low_usability": 0}
        
        relevance_scores = []
        verifiability_scores = []
        usability_scores = []
        
        for photo in photos:
            metadata = photo.get('metadata', {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata) if metadata else {}
            
            if metadata.get('is_ai_generated'):
                ai_detected += 1
                if photo.get('status') == 'rejected':
                    rejection_reasons['ai_generated'] += 1
            
            if photo.get('status') == 'rejected':
                if photo.get('relevance_score', 10) < 7:
                    rejection_reasons['low_relevance'] += 1
                usability = metadata.get('usability_score', 10)
                if usability < 6:
                    rejection_reasons['low_usability'] += 1
            
            if photo.get('relevance_score'):
                relevance_scores.append(photo['relevance_score'])
            if photo.get('verifiability_score'):
                verifiability_scores.append(photo['verifiability_score'])
            if metadata.get('usability_score'):
                usability_scores.append(metadata['usability_score'])
        
        # Group photos by story
        photos_by_story = {}
        for photo in photos:
            story_id = str(photo['story_research_id'])
            if story_id not in photos_by_story:
                photos_by_story[story_id] = {
                    "story_research_id": story_id,
                    "story_title": photo['story_title'],
                    "queries_used": set(),
                    "photos": [],
                    "approved_count": 0,
                    "rejected_count": 0
                }
            
            if photo.get('search_query'):
                photos_by_story[story_id]['queries_used'].add(photo['search_query'])
            
            metadata = photo.get('metadata', {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata) if metadata else {}
            
            photos_by_story[story_id]['photos'].append({
                "id": str(photo['id']),
                "image_url": photo['image_url'],
                "status": photo['status'],
                "scores": {
                    "relevance": photo.get('relevance_score'),
                    "verifiability": photo.get('verifiability_score'),
                    "usability": metadata.get('usability_score')
                },
                "is_ai_generated": metadata.get('is_ai_generated', False),
                "is_hero": metadata.get('placement', {}).get('enabled', False),
                "placement": metadata.get('placement'),
                "source": {
                    "page_url": photo.get('source_page_url'),
                    "attribution": photo.get('source_attribution')
                },
                "ai_analysis": {
                    "description": photo.get('description'),
                    "generated_caption": photo.get('caption')
                },
                "search_query": photo.get('search_query'),
                "concept_tag": photo.get('concept_tag')
            })
            
            if photo.get('status') == 'approved':
                photos_by_story[story_id]['approved_count'] += 1
            elif photo.get('status') == 'rejected':
                photos_by_story[story_id]['rejected_count'] += 1
        
        # Convert sets to lists and finalize
        stories_list = []
        for story_data in photos_by_story.values():
            story_data['queries_used'] = list(story_data['queries_used'])
            stories_list.append(story_data)
        
        return {
            "phase": "photo_research",
            "summary": {
                "stories_processed": len(photos_by_story),
                "total_photos_found": total,
                "approved": approved,
                "rejected": rejected,
                "ai_detected": ai_detected,
                "rejection_reasons": rejection_reasons
            },
            "score_averages": {
                "relevance": sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0,
                "verifiability": sum(verifiability_scores) / len(verifiability_scores) if verifiability_scores else 0,
                "usability": sum(usability_scores) / len(usability_scores) if usability_scores else 0
            },
            "photos_by_story": stories_list
        }


def get_phase5_data(run_id: str) -> Dict[str, Any]:
    """Get comprehensive Phase 5 (Thumbnail Generation) data for visualization."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT 
                st.id, st.story_generation_id, st.concept_number, st.concept_type,
                st.scene_description, st.full_prompt, st.image_url,
                st.status, st.is_selected, st.generation_metadata,
                st.created_at, st.generated_at,
                sg.hook_title, sg.subtitle, sg.domain_tag
            FROM story_thumbnails st
            JOIN story_generations sg ON st.story_generation_id = sg.id
            WHERE st.pipeline_run_id = %s
            ORDER BY sg.id, st.concept_number ASC
        """, (run_id,))
        thumbnails = cur.fetchall()
        
        # Calculate stats
        total = len(thumbnails)
        generated = len([t for t in thumbnails if t.get('status') == 'generated'])
        failed = len([t for t in thumbnails if t.get('status') == 'failed'])
        selected = len([t for t in thumbnails if t.get('is_selected')])
        
        # Concept type breakdown
        concept_breakdown = {"literal": 0, "symbolic": 0, "atmospheric": 0}
        generation_times = []
        
        # Group thumbnails by story
        thumbnails_by_story = {}
        for thumb in thumbnails:
            story_id = str(thumb['story_generation_id'])
            
            if story_id not in thumbnails_by_story:
                thumbnails_by_story[story_id] = {
                    "story_generation_id": story_id,
                    "hook_title": thumb['hook_title'],
                    "subtitle": thumb['subtitle'],
                    "domain_tag": thumb['domain_tag'],
                    "thumbnails": []
                }
            
            metadata = thumb.get('generation_metadata', {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata) if metadata else {}
            
            gen_time = metadata.get('generation_time_seconds', 0)
            if gen_time:
                generation_times.append(gen_time)
            
            concept_type = thumb.get('concept_type', 'unknown')
            if concept_type in concept_breakdown:
                concept_breakdown[concept_type] += 1
            
            thumbnails_by_story[story_id]['thumbnails'].append({
                "id": str(thumb['id']),
                "concept_number": thumb['concept_number'],
                "concept_type": concept_type,
                "is_selected": thumb.get('is_selected', False),
                "status": thumb['status'],
                "scene_description": thumb['scene_description'],
                "full_prompt": thumb.get('full_prompt'),
                "image_url": thumb['image_url'],
                "generation_metadata": metadata
            })
        
        return {
            "phase": "thumbnail_generation",
            "summary": {
                "stories_processed": len(thumbnails_by_story),
                "total_thumbnails": total,
                "generated": generated,
                "failed": failed,
                "selected": selected,
                "average_generation_time_seconds": sum(generation_times) // len(generation_times) if generation_times else 0
            },
            "concept_type_breakdown": concept_breakdown,
            "thumbnails_by_story": list(thumbnails_by_story.values())
        }


def get_slides_for_generation(generation_id: str) -> List[Dict[str, Any]]:
    """Get all slides for a story generation."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT 
                id, slide_order, text_content, document_type_tag, paragraph_count
            FROM story_slides
            WHERE story_generation_id = %s
            ORDER BY slide_order
        """, (generation_id,))
        return cur.fetchall()


def update_funnel_data(run_id: str, funnel_data: Dict[str, Any]) -> bool:
    """Update funnel data for lead generation phase."""
    run = get_pipeline_run(run_id)
    if not run:
        return False
    
    phases = run.get('phases', [])
    if isinstance(phases, str):
        phases = json.loads(phases)
    
    for p in phases:
        if p.get('phase') == 'lead_generation':
            p['funnel_data'] = funnel_data
            break
    
    return update_pipeline_run(run_id, phases=phases)


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
    """Cancel a pipeline run and delete all data created during it (keeps the run record)."""
    return _cleanup_pipeline_run(run_id, hard_delete_run_record=False, set_status="cancelled")


def delete_run_and_cleanup(run_id: str) -> Dict[str, Any]:
    """Hard-delete a pipeline run and all associated data (removes the run record)."""
    return _cleanup_pipeline_run(run_id, hard_delete_run_record=True, set_status=None)


def _cleanup_pipeline_run(run_id: str, hard_delete_run_record: bool, set_status: Optional[str]) -> Dict[str, Any]:
    """
    Delete all records associated with a pipeline run in safe dependency order.

    Important:
    - Some tables are not owned by the pipeline manager but may reference pipeline outputs
      (e.g. `story_assemblies`, `scheduled_posts`). We delete those rows if they reference
      generations from this run to avoid FK failures when deleting `story_generations`.
    - `discovery_topics.origin_lead_id` may reference leads; we NULL it before deleting leads.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Fetch generation ids once (used by slides/assemblies/schedule deletes)
            cur.execute("SELECT id FROM story_generations WHERE pipeline_run_id = %s", (run_id,))
            generation_ids = [row["id"] for row in (cur.fetchall() or [])]

            # Delete scheduled posts and assemblies that reference generations from this run (if those tables exist)
            try:
                cur.execute(
                    "DELETE FROM scheduled_posts WHERE story_generation_id = ANY(%s)",
                    (generation_ids,)
                )
                scheduled_posts_deleted = cur.rowcount or 0
            except Exception:
                scheduled_posts_deleted = 0

            try:
                cur.execute(
                    "DELETE FROM story_assemblies WHERE story_generation_id = ANY(%s)",
                    (generation_ids,)
                )
                assemblies_deleted = cur.rowcount or 0
            except Exception:
                assemblies_deleted = 0

            # Thumbnails
            cur.execute("DELETE FROM story_thumbnails WHERE pipeline_run_id = %s", (run_id,))
            thumbnails_deleted = cur.rowcount or 0

            # Slides (via generation ids)
            if generation_ids:
                cur.execute("DELETE FROM story_slides WHERE story_generation_id = ANY(%s)", (generation_ids,))
                slides_deleted = cur.rowcount or 0
            else:
                slides_deleted = 0

            # Photos
            cur.execute("DELETE FROM story_photos WHERE pipeline_run_id = %s", (run_id,))
            photos_deleted = cur.rowcount or 0

            # Story generations
            cur.execute("DELETE FROM story_generations WHERE pipeline_run_id = %s", (run_id,))
            generations_deleted = cur.rowcount or 0

            # Story research
            cur.execute("DELETE FROM story_research WHERE pipeline_run_id = %s", (run_id,))
            research_deleted = cur.rowcount or 0

            # Make sure we don't violate discovery_topics.origin_lead_id -> leads(id)
            try:
                cur.execute(
                    """
                    UPDATE discovery_topics
                    SET origin_lead_id = NULL
                    WHERE origin_lead_id IN (SELECT id FROM leads WHERE pipeline_run_id = %s)
                    """,
                    (run_id,),
                )
            except Exception:
                # discovery_topics may not exist in some environments
                pass

            # Leads
            cur.execute("DELETE FROM leads WHERE pipeline_run_id = %s", (run_id,))
            leads_deleted = cur.rowcount or 0

            # Pipeline story statuses
            cur.execute("DELETE FROM pipeline_story_status WHERE pipeline_run_id = %s", (run_id,))
            story_status_deleted = cur.rowcount or 0

            run_record_deleted = 0
            if hard_delete_run_record:
                cur.execute("DELETE FROM pipeline_runs WHERE id = %s", (run_id,))
                run_record_deleted = cur.rowcount or 0
            elif set_status:
                cur.execute(
                    """
                    UPDATE pipeline_runs
                    SET status = %s, completed_at = COALESCE(completed_at, now()), updated_at = now()
                    WHERE id = %s
                    """,
                    (set_status, run_id),
                )

            conn.commit()
            return {
                "success": True,
                "deleted": {
                    "leads": leads_deleted,
                    "research": research_deleted,
                    "generations": generations_deleted,
                    "slides": slides_deleted,
                    "photos": photos_deleted,
                    "thumbnails": thumbnails_deleted,
                    "pipeline_story_status": story_status_deleted,
                    "story_assemblies": assemblies_deleted,
                    "scheduled_posts": scheduled_posts_deleted,
                    "pipeline_run": run_record_deleted,
                },
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

