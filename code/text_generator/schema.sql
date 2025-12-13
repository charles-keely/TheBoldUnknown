-- Schema update for Text Generator

-- 1. Table for high-level story generation (Cover info)
CREATE TABLE IF NOT EXISTS public.story_generations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_research_id UUID NOT NULL REFERENCES public.story_research(id),
    
    -- Selected Cover Content
    hook_title TEXT NOT NULL,
    subtitle TEXT NOT NULL,
    domain_tag TEXT NOT NULL,
    
    -- Raw generation data (storing the 3 options + reasoning)
    generation_metadata JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    model_used TEXT DEFAULT 'gpt-5.2'
);

-- 2. Table for narrative slides
CREATE TABLE IF NOT EXISTS public.story_slides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_generation_id UUID NOT NULL REFERENCES public.story_generations(id),
    
    slide_order INTEGER NOT NULL,
    text_content TEXT NOT NULL,
    document_type_tag TEXT NOT NULL,
    paragraph_count INTEGER,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Add text columns to story_photos
ALTER TABLE public.story_photos 
ADD COLUMN IF NOT EXISTS caption TEXT,
ADD COLUMN IF NOT EXISTS source_attribution TEXT,
ADD COLUMN IF NOT EXISTS concept_tag TEXT,
ADD COLUMN IF NOT EXISTS text_generated_at TIMESTAMP WITH TIME ZONE;
