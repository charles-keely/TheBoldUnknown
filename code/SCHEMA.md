-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.discovery_topics (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  topic text NOT NULL UNIQUE,
  last_searched_at timestamp with time zone,
  origin_lead_id uuid,
  status text DEFAULT 'active'::text CHECK (status = ANY (ARRAY['active'::text, 'exhausted'::text, 'paused'::text])),
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT discovery_topics_pkey PRIMARY KEY (id),
  CONSTRAINT discovery_topics_origin_lead_id_fkey FOREIGN KEY (origin_lead_id) REFERENCES public.leads(id)
);
CREATE TABLE public.ig_access_tokens (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  access_token text NOT NULL,
  token_type text DEFAULT 'bearer'::text,
  expires_at timestamp with time zone NOT NULL,
  obtained_at timestamp with time zone DEFAULT now(),
  last_used_at timestamp with time zone,
  refresh_count integer DEFAULT 0,
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT ig_access_tokens_pkey PRIMARY KEY (id)
);
CREATE TABLE public.leads (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  title text NOT NULL,
  url text NOT NULL,
  summary text,
  embedding USER-DEFINED,
  brand_score integer,
  virality_score integer,
  status text DEFAULT 'new'::text CHECK (status = ANY (ARRAY['new'::text, 'approved'::text, 'rejected'::text, 'published'::text])),
  source_origin text,
  created_at timestamp with time zone DEFAULT now(),
  viral_hook text,
  interestingness_score integer,
  substance_analysis text,
  published_at timestamp with time zone,
  pipeline_run_id uuid,
  CONSTRAINT leads_pkey PRIMARY KEY (id),
  CONSTRAINT leads_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id)
);
CREATE TABLE public.pipeline_runs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  mode text NOT NULL CHECK (mode = ANY (ARRAY['auto'::text, 'step'::text])),
  status text NOT NULL DEFAULT 'pending'::text CHECK (status = ANY (ARRAY['pending'::text, 'running'::text, 'paused'::text, 'completed'::text, 'failed'::text, 'cancelled'::text])),
  current_phase text,
  current_phase_index integer DEFAULT 0,
  total_phases integer DEFAULT 5,
  started_at timestamp with time zone,
  completed_at timestamp with time zone,
  error_message text,
  config jsonb DEFAULT '{}'::jsonb,
  stats jsonb DEFAULT '{"photos_found": 0, "leads_approved": 0, "photos_approved": 0, "leads_discovered": 0, "research_completed": 0, "thumbnails_generated": 0, "generations_completed": 0}'::jsonb,
  phases jsonb DEFAULT '[]'::jsonb,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT pipeline_runs_pkey PRIMARY KEY (id)
);
CREATE TABLE public.pipeline_story_status (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  pipeline_run_id uuid,
  lead_id uuid,
  story_research_id uuid,
  story_generation_id uuid,
  title text,
  phase_statuses jsonb DEFAULT '{}'::jsonb,
  error_log jsonb DEFAULT '[]'::jsonb,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT pipeline_story_status_pkey PRIMARY KEY (id),
  CONSTRAINT pipeline_story_status_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id)
);
CREATE TABLE public.processed_urls (
  url text NOT NULL,
  processed_at timestamp with time zone DEFAULT now(),
  CONSTRAINT processed_urls_pkey PRIMARY KEY (url)
);
CREATE TABLE public.schedule_approvals (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  approved_at timestamp with time zone DEFAULT now(),
  posts_approved integer NOT NULL,
  notes text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT schedule_approvals_pkey PRIMARY KEY (id)
);
CREATE TABLE public.scheduled_posts (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  story_generation_id uuid NOT NULL,
  assembly_id uuid,
  scheduled_at timestamp with time zone NOT NULL,
  position integer NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'scheduled'::text,
  approved_at timestamp with time zone,
  published_at timestamp with time zone,
  instagram_media_id text,
  error_message text,
  retry_count integer DEFAULT 0,
  saves_count integer,
  impressions_count integer,
  profile_visits_count integer,
  carousel_completion_rate numeric,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT scheduled_posts_pkey PRIMARY KEY (id),
  CONSTRAINT scheduled_posts_story_generation_id_fkey FOREIGN KEY (story_generation_id) REFERENCES public.story_generations(id),
  CONSTRAINT scheduled_posts_assembly_id_fkey FOREIGN KEY (assembly_id) REFERENCES public.story_assemblies(id)
);
CREATE TABLE public.story_assemblies (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  story_generation_id uuid NOT NULL,
  assembly_data jsonb NOT NULL,
  status text NOT NULL DEFAULT 'draft'::text CHECK (status = ANY (ARRAY['draft'::text, 'in_progress'::text, 'finalized'::text])),
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  rendered_files jsonb,
  CONSTRAINT story_assemblies_pkey PRIMARY KEY (id),
  CONSTRAINT story_assemblies_story_generation_id_fkey FOREIGN KEY (story_generation_id) REFERENCES public.story_generations(id)
);
CREATE TABLE public.story_generations (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  story_research_id uuid NOT NULL,
  hook_title text NOT NULL,
  subtitle text NOT NULL,
  domain_tag text NOT NULL,
  generation_metadata jsonb,
  created_at timestamp with time zone DEFAULT now(),
  model_used text DEFAULT 'gpt-5.2'::text,
  instagram_caption text,
  hashtags ARRAY,
  is_enabled boolean NOT NULL DEFAULT true,
  approved_for_assembly boolean NOT NULL DEFAULT false,
  approved_for_assembly_at timestamp with time zone,
  pipeline_run_id uuid,
  CONSTRAINT story_generations_pkey PRIMARY KEY (id),
  CONSTRAINT story_generations_story_research_id_fkey FOREIGN KEY (story_research_id) REFERENCES public.story_research(id),
  CONSTRAINT story_generations_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id)
);
CREATE TABLE public.story_memory (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  source_type text NOT NULL CHECK (source_type = ANY (ARRAY['lead'::text, 'story_generation'::text, 'story_assembly'::text, 'scheduled_post'::text])),
  source_id uuid NOT NULL,
  lead_id uuid,
  canonical_title text,
  canonical_summary text,
  canonical_url text,
  dedupe_text text NOT NULL,
  embedding USER-DEFINED,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  is_active_for_dedupe boolean NOT NULL DEFAULT true,
  CONSTRAINT story_memory_pkey PRIMARY KEY (id)
);
CREATE TABLE public.story_photos (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  story_research_id uuid NOT NULL,
  image_url text NOT NULL,
  source_page_url text,
  search_query text,
  description text,
  relevance_score integer CHECK (relevance_score >= 0 AND relevance_score <= 10),
  verifiability_score integer CHECK (verifiability_score >= 0 AND verifiability_score <= 10),
  status text DEFAULT 'potential'::text CHECK (status = ANY (ARRAY['potential'::text, 'approved'::text, 'rejected'::text])),
  metadata jsonb DEFAULT '{}'::jsonb,
  created_at timestamp with time zone DEFAULT now(),
  caption text,
  source_attribution text,
  concept_tag text,
  text_generated_at timestamp with time zone,
  pipeline_run_id uuid,
  CONSTRAINT story_photos_pkey PRIMARY KEY (id),
  CONSTRAINT story_photos_story_research_id_fkey FOREIGN KEY (story_research_id) REFERENCES public.story_research(id),
  CONSTRAINT story_photos_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id)
);
CREATE TABLE public.story_research (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  lead_id uuid NOT NULL UNIQUE,
  discovery_topic_id uuid,
  status text NOT NULL DEFAULT 'queued'::text CHECK (status = ANY (ARRAY['queued'::text, 'in_progress'::text, 'completed'::text, 'skipped'::text])),
  priority integer,
  notes text,
  created_at timestamp with time zone DEFAULT now(),
  started_at timestamp with time zone,
  completed_at timestamp with time zone,
  research_data jsonb,
  primary_sources ARRAY,
  primary_source_urls ARRAY,
  pipeline_run_id uuid,
  CONSTRAINT story_research_pkey PRIMARY KEY (id),
  CONSTRAINT story_research_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id),
  CONSTRAINT story_research_discovery_topic_id_fkey FOREIGN KEY (discovery_topic_id) REFERENCES public.discovery_topics(id),
  CONSTRAINT story_research_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id)
);
CREATE TABLE public.story_slides (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  story_generation_id uuid NOT NULL,
  slide_order integer NOT NULL,
  text_content text NOT NULL,
  document_type_tag text NOT NULL,
  paragraph_count integer,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT story_slides_pkey PRIMARY KEY (id),
  CONSTRAINT story_slides_story_generation_id_fkey FOREIGN KEY (story_generation_id) REFERENCES public.story_generations(id)
);
CREATE TABLE public.story_thumbnails (
  id uuid NOT NULL,
  story_generation_id uuid,
  concept_number integer CHECK (concept_number >= 1 AND concept_number <= 3),
  concept_type text CHECK (concept_type = ANY (ARRAY['literal'::text, 'symbolic'::text, 'atmospheric'::text])),
  scene_description text,
  full_prompt text,
  image_url text,
  status text CHECK (status = ANY (ARRAY['pending'::text, 'generating'::text, 'generated'::text, 'approved'::text, 'rejected'::text, 'failed'::text])),
  is_selected boolean DEFAULT false,
  generation_metadata jsonb,
  created_at timestamp without time zone DEFAULT now(),
  generated_at timestamp without time zone,
  selected_at timestamp without time zone,
  pipeline_run_id uuid,
  CONSTRAINT story_thumbnails_pkey PRIMARY KEY (id),
  CONSTRAINT story_thumbnails_story_generation_id_fkey FOREIGN KEY (story_generation_id) REFERENCES public.story_generations(id),
  CONSTRAINT story_thumbnails_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id)
);