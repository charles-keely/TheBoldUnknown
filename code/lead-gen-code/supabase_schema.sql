-- Enable the pgvector extension to work with embeddings
create extension if not exists vector;

-- Table to track processed URLs to avoid expensive vector checks for exact duplicates
create table processed_urls (
  url text primary key,
  processed_at timestamp with time zone default now()
);

-- Table to store the actual story leads
create table leads (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  url text not null,
  summary text,
  -- 1536 dimensions is standard for openai text-embedding-3-small
  embedding vector(1536),
  brand_score integer,
  virality_score integer,
  viral_hook text,  -- The shareable angle identified during virality check
  status text check (status in ('new', 'approved', 'rejected', 'published')) default 'new',
  source_origin text,
  created_at timestamp with time zone default now()
);

-- Migration for existing databases:
-- ALTER TABLE leads ADD COLUMN IF NOT EXISTS viral_hook text;

-- Index for faster vector similarity search
-- Note: You might need to insert some data before creating an IVFFLAT index, 
-- or use HNSW index if your Supabase version supports it (recommended for performance).
create index on leads using hnsw (embedding vector_cosine_ops);

-- Table to store topics for the "Active Discovery" engine
create table discovery_topics (
  id uuid primary key default gen_random_uuid(),
  topic text not null unique,
  last_searched_at timestamp with time zone,
  origin_lead_id uuid references leads(id),
  status text check (status in ('active', 'exhausted', 'paused')) default 'active',
  created_at timestamp with time zone default now()
);

-- Seed initial topics (Optional, but good practice)
insert into discovery_topics (topic) values 
('Time Dilation'), 
('Unexplained Archeology'), 
('Bioluminescence'),
('Cognitive Anomalies'),
('Dark Forest Theory');

