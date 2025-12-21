-- Pipeline Manager Database Schema
-- Run this migration to add pipeline management capabilities

-- =============================================================================
-- NEW TABLES
-- =============================================================================

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

-- =============================================================================
-- MODIFICATIONS TO EXISTING TABLES (for data cleanup tracking)
-- =============================================================================

-- Add pipeline_run_id to track which pipeline run created each record
ALTER TABLE leads ADD COLUMN IF NOT EXISTS pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_research ADD COLUMN IF NOT EXISTS pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_generations ADD COLUMN IF NOT EXISTS pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_photos ADD COLUMN IF NOT EXISTS pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_thumbnails ADD COLUMN IF NOT EXISTS pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;

-- Indexes for efficient cleanup queries
CREATE INDEX IF NOT EXISTS idx_leads_pipeline_run ON leads(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_story_research_pipeline_run ON story_research(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_story_generations_pipeline_run ON story_generations(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_story_photos_pipeline_run ON story_photos(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_story_thumbnails_pipeline_run ON story_thumbnails(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;

-- =============================================================================
-- EXAMPLE DATA STRUCTURES (for reference)
-- =============================================================================

-- Example phase_statuses JSON:
-- {
--   "lead_generation": {"status": "completed", "started_at": "...", "completed_at": "...", "count": 15},
--   "curation": {"status": "completed", "result": {"approved": true, "reasoning": "..."}},
--   "story_research": {"status": "in_progress", "started_at": "..."},
--   "text_generation": {"status": "pending"},
--   "photo_research": {"status": "pending"},
--   "thumbnail_generation": {"status": "pending"}
-- }

-- Example stats JSON:
-- {
--   "leads_discovered": 247,
--   "leads_approved": 12,
--   "research_completed": 12,
--   "generations_completed": 12,
--   "photos_found": 47,
--   "photos_approved": 32,
--   "thumbnails_generated": 36
-- }

-- Example phases JSON (stored per-run):
-- [
--   {"phase": "lead_generation", "status": "completed", "order": 1, "started_at": "...", "completed_at": "...", "total_items": 247, "completed_items": 12},
--   {"phase": "story_research", "status": "completed", "order": 2, ...},
--   {"phase": "text_generation", "status": "running", "order": 3, ...},
--   {"phase": "photo_research", "status": "pending", "order": 4},
--   {"phase": "thumbnail_generation", "status": "pending", "order": 5}
-- ]

