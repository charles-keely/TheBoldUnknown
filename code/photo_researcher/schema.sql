CREATE TABLE IF NOT EXISTS story_photos (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    story_research_id uuid NOT NULL,
    image_url text NOT NULL,
    source_page_url text,
    search_query text,
    description text,
    relevance_score integer CHECK (relevance_score >= 0 AND relevance_score <= 10),
    verifiability_score integer CHECK (verifiability_score >= 0 AND verifiability_score <= 10),
    status text DEFAULT 'potential' CHECK (status = ANY (ARRAY['potential', 'approved', 'rejected'])),
    metadata jsonb DEFAULT '{}',
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT story_photos_pkey PRIMARY KEY (id),
    CONSTRAINT story_photos_story_research_id_fkey FOREIGN KEY (story_research_id) REFERENCES story_research(id)
);
