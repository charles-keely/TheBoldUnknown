-- Durable semantic dedupe index ("story memory")
-- Keeps a persistent embedding record even if you later delete/prune rows from `leads`.

-- pgvector is required for the embedding column
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.story_memory (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Where this memory entry came from
  source_type text NOT NULL CHECK (source_type IN ('lead', 'story_generation', 'story_assembly', 'scheduled_post')),
  source_id uuid NOT NULL,

  -- Optional linkage back to the originating lead (NOT a foreign key on purpose;
  -- we want memory to survive lead cleanup).
  lead_id uuid,

  -- Canonical fields (best-effort; used for debugging + future exact-match heuristics)
  canonical_title text,
  canonical_summary text,
  canonical_url text,

  -- Text used to generate the embedding (so we can re-embed deterministically)
  dedupe_text text NOT NULL,

  -- Embedding (OpenAI text-embedding-3-small = 1536 dims)
  embedding vector(1536),

  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),

  UNIQUE (source_type, source_id)
);

-- Vector similarity index (cosine distance)
CREATE INDEX IF NOT EXISTS idx_story_memory_embedding_hnsw
  ON public.story_memory
  USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_story_memory_lead_id ON public.story_memory(lead_id);
CREATE INDEX IF NOT EXISTS idx_story_memory_canonical_url ON public.story_memory(canonical_url);


