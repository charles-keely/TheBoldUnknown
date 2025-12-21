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

-- =============================================================================
-- Durable semantic dedupe index ("story memory")
-- =============================================================================
-- Keeps a persistent embedding record even if you later delete/prune rows from `leads`.

create table if not exists public.story_memory (
  id uuid primary key default gen_random_uuid(),
  source_type text not null check (source_type in ('lead', 'story_generation', 'story_assembly', 'scheduled_post')),
  source_id uuid not null,
  lead_id uuid,
  canonical_title text,
  canonical_summary text,
  canonical_url text,
  dedupe_text text not null,
  embedding vector(1536),
  is_active_for_dedupe boolean not null default true,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now(),
  unique (source_type, source_id)
);

create index if not exists idx_story_memory_embedding_hnsw
  on public.story_memory using hnsw (embedding vector_cosine_ops);

create index if not exists idx_story_memory_lead_id on public.story_memory(lead_id);
create index if not exists idx_story_memory_canonical_url on public.story_memory(canonical_url);
create index if not exists idx_story_memory_is_active_for_dedupe on public.story_memory(is_active_for_dedupe);

-- Auto-mute lead-based memory if the lead is deleted or rejected.
-- NOTE: We only mute source_type='lead' rows. Published/assembled memory remains.

create or replace function public.story_memory_mute_on_lead_delete()
returns trigger as $$
begin
  update public.story_memory
  set is_active_for_dedupe = false,
      updated_at = now()
  where source_type = 'lead'
    and source_id = old.id;
  return old;
end;
$$ language plpgsql;

drop trigger if exists trg_story_memory_mute_on_lead_delete on public.leads;
create trigger trg_story_memory_mute_on_lead_delete
after delete on public.leads
for each row
execute function public.story_memory_mute_on_lead_delete();

create or replace function public.story_memory_mute_on_lead_reject()
returns trigger as $$
begin
  if new.status = 'rejected' then
    update public.story_memory
    set is_active_for_dedupe = false,
        updated_at = now()
    where source_type = 'lead'
      and source_id = new.id;
  end if;
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_story_memory_mute_on_lead_reject on public.leads;
create trigger trg_story_memory_mute_on_lead_reject
after update of status on public.leads
for each row
execute function public.story_memory_mute_on_lead_reject();

