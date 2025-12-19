-- Story assemblies table
-- Stores the finalized arrangement of slides for Instagram export

CREATE TABLE IF NOT EXISTS public.story_assemblies (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    story_generation_id uuid NOT NULL,
    assembly_data jsonb NOT NULL,
    -- assembly_data schema:
    -- {
    --   "version": 1,
--   "selected_generation_id": "uuid", -- chosen title/subtitle option (story_generations row)
    --   "selected_thumbnail_id": "uuid",
    --   "slides": [
    --     {
    --       "id": "uuid",
    --       "type": "cover" | "text" | "photo",
    --       "template": "cover3" | "editorial3" | "photos1",
    --       "visible": true | false,
    --       "content": { ... },
    --       "source_slide_id": "uuid" (optional, links to story_slides),
    --       "source_photo_id": "uuid" (optional, links to story_photos)
    --     }
    --   ],
    --   "metadata": { "created_at": "...", "updated_at": "..." }
    -- }
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'in_progress', 'finalized')),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT story_assemblies_pkey PRIMARY KEY (id),
    CONSTRAINT story_assemblies_story_generation_id_fkey FOREIGN KEY (story_generation_id) REFERENCES public.story_generations(id)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_story_assemblies_generation ON public.story_assemblies(story_generation_id);
CREATE INDEX IF NOT EXISTS idx_story_assemblies_status ON public.story_assemblies(status);
CREATE INDEX IF NOT EXISTS idx_story_assemblies_updated ON public.story_assemblies(updated_at DESC);

-- Auto-update updated_at timestamp on every update
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_story_assemblies_updated_at ON public.story_assemblies;
CREATE TRIGGER update_story_assemblies_updated_at
    BEFORE UPDATE ON public.story_assemblies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
