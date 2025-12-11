-- Enable the vector extension if not already enabled (required for the embedding column)
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Create Enums for type safety (optional but recommended, otherwise use text check constraints)
-- We'll use text with check constraints to keep it simple and compatible with existing text columns
-- Discovery Types: 'vertical', 'lateral', 'wildcard', 'gravity'
-- Queue Types: 'vertical', 'lateral', 'wildcard'

-- 2. Modify 'leads' table
ALTER TABLE leads 
  ADD COLUMN IF NOT EXISTS score_breakdown JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS keywords TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS discovery_type TEXT CHECK (discovery_type IN ('vertical', 'lateral', 'wildcard', 'gravity'));

-- 3. Modify 'search_queue' table
ALTER TABLE search_queue
  ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'lateral' CHECK (type IN ('vertical', 'lateral', 'wildcard'));

-- 4. Clean up and re-seed Brand Pillars (Optional: run this if you want to apply the new seed_pillars.sql immediately)
-- TRUNCATE TABLE brand_pillars;
-- [Insert statements from seed_pillars.sql would go here]

