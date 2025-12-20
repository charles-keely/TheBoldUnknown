# TheBoldUnknown — Content Pipeline

**A cinematic, intelligent exploration of the hidden strangeness woven through reality.**

TheBoldUnknown is an automated content pipeline that discovers, researches, and produces visually rich Instagram carousel stories about surprising, counterintuitive, and quietly uncanny phenomena. The system operates through six interconnected modules that transform raw internet sources into publication-ready content.

---

## 🎯 Brand Identity

TheBoldUnknown is defined by its **lens**, not by specific topics:

- **Grounded & Rational** — Evidence-minded, never conspiratorial
- **Quietly Strange** — "Wait... that is actually strange" moments
- **Cinematic** — Atmospheric, visually expressive storytelling
- **Intellectually Curious** — Calm, confident, precise

**What qualifies as a story?** Any topic from any domain that includes:
- A surprising, counterintuitive, or unexplained detail
- A pattern that defies intuition or expectation
- A documented event with puzzling elements
- Research suggesting something unexpected or unresolved

**Hard exclusions:** Celebrity gossip, partisan politics, rage-bait, low-evidence conspiracy claims.

---

## 🔄 Pipeline Overview

The complete workflow transforms internet sources into Instagram-ready content:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           TheBoldUnknown Pipeline                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌──────────────────┐                                                          │
│   │  LEAD GENERATOR  │  ← RSS Feeds (~35 sources)                               │
│   │   (Discovery)    │  ← Perplexity Active Discovery                           │
│   └────────┬─────────┘                                                          │
│            │                                                                     │
│            │  5-stage filter: URL dedup → Smart Gatekeeper → Semantic dedup     │
│            │                  → Virality check (≥78) → Brand lens (≥70)         │
│            │                                                                     │
│            ▼                                                                     │
│   ┌──────────────────┐                                                          │
│   │     CURATOR      │  Weekly selection of best stories                        │
│   │   (Selection)    │  AI-driven editorial curation                            │
│   └────────┬─────────┘                                                          │
│            │                                                                     │
│            │  Approves leads → Queues for research                              │
│            │                                                                     │
│            ▼                                                                     │
│   ┌──────────────────┐                                                          │
│   │ STORY RESEARCHER │  Phase 1: Ground Truth (Perplexity)                      │
│   │    (Research)    │  Phase 2: Hook Identification (GPT-4o)                   │
│   └────────┬─────────┘  Optional: Deep Dive on visual/emotional details         │
│            │                                                                     │
│            ▼                                                                     │
│   ┌──────────────────┐                                                          │
│   │ PHOTO RESEARCHER │  AI query generation → Google Image Search               │
│   │   (Visuals)      │  Deep verification: scraping + GPT-5.1 Vision            │
│   └────────┬─────────┘  Quality scoring: Relevance, Verifiability, Usability    │
│            │                                                                     │
│            ▼                                                                     │
│   ┌──────────────────┐                                                          │
│   │  TEXT GENERATOR  │  Story slides (7-9 slides) → Cover options (6)           │
│   │    (Writing)     │  Photo captions (documentary style)                      │
│   └────────┬─────────┘                                                          │
│            │                                                                     │
│            ▼                                                                     │
│   ┌──────────────────┐                                                          │
│   │THUMBNAIL GENERATOR│ GPT-5.2 concept generation (3 concepts)                 │
│   │   (Cover Art)    │  Nano Banana (Gemini) image generation                   │
│   └────────┬─────────┘  Interactive preview for selection                       │
│            │                                                                     │
│            ▼                                                                     │
│   ┌──────────────────┐                                                          │
│   │  PRE-ASSEMBLER   │  Web-based carousel assembly editor                      │
│   │    (Layout)      │  Drag-and-drop ordering, text editing, approval          │
│   └────────┬─────────┘                                                          │
│            │                                                                     │
│            ▼                                                                     │
│   ┌──────────────────┐                                                          │
│   │    ASSEMBLER     │  Playwright headless rendering                           │
│   │  (PNG Export)    │  HTML templates → 1080×1350 PNG carousel slides          │
│   └────────┬─────────┘                                                          │
│            │                                                                     │
│            ▼                                                                     │
│   ┌──────────────────┐                                                          │
│   │    SCHEDULER     │  Upload PNGs to Supabase Storage                         │
│   │   (Publisher)    │  Publish carousel via Instagram Graph API                │
│   └──────────────────┘                                                          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Module Breakdown

### 1. Lead Generator (`lead_generator/`)

**Purpose:** Autonomously scouts the internet for "quietly strange" stories and filters them through a strict brand lens.

**Pipeline:**
1. **Ingestion** — RSS feeds (~35 sources) + Perplexity active discovery
2. **URL Deduplication** — Instant check against `processed_urls`
3. **Smart Gatekeeper** — Batch analysis (20 titles), rejects politics/gossip
4. **Semantic Deduplication** — Vector embeddings, 75% similarity threshold
5. **Virality Check** — Must score ≥78/100
6. **Brand Lens Check** — Must score ≥70/100
7. **Fractal Expansion** — Extracts 2-3 new search topics from each accepted lead

**Models:** GPT-4o (filtering), GPT-4o-mini (batch operations), Perplexity Sonar Pro (discovery)

**Key Tables:** `leads`, `discovery_topics`, `processed_urls`

```bash
cd lead_generator
python main.py run              # Full workflow
python main.py run --source rss # RSS only
python main.py run --source perplexity  # Discovery only
```

---

### 2. Curator (`curator/`)

**Purpose:** Selects weekly stories from the leads pool and queues them for research.

**How it works:**
1. Fetches candidate leads created after the most recently published story
2. Sends candidates to LLM curator for editorial selection
3. Marks selected leads as `approved`
4. Queues them in `story_research` with curator reasoning

**Model:** GPT-5.1

**Output:** `curation_results.txt` with selection reasoning

```bash
cd curator
python main.py --dry-run  # Preview without DB changes
python main.py            # Execute curation
```

---

### 3. Story Researcher (`story_researcher/`)

**Purpose:** Gathers comprehensive research to prepare stories for Instagram post creation.

**Pipeline:**
1. **Phase 1 (Ground Truth)** — Perplexity gathers facts: who, what, where, when, why, visual details
2. **Phase 2 (The Hook)** — GPT-4o identifies the "Wait... What?" angle
3. **Optional Deep Dive** — Additional research on specific visual/emotional elements

**Models:** Perplexity Sonar Pro (research), GPT-4o (angle identification)

**Output:** JSONB in `story_research.research_data`:
```json
{
  "ground_truth": "Comprehensive facts...",
  "follow_up": {
    "question": "Specific follow-up...",
    "answer": "Deep dive results..."
  }
}
```

```bash
cd code
PYTHONPATH=. ./story_researcher/venv/bin/python -m story_researcher.main --single
```

---

### 4. Photo Researcher (`photo_researcher/`)

**Purpose:** Finds, verifies, and curates images for stories.

**Pipeline:**
1. **Generate** — GPT-5.1 creates specific search queries from research
2. **Search** — Google Images Custom Search (top 5 per query)
3. **Validate** — Check URL accessibility
4. **Scrape** — Extract captions and context from source pages
5. **Analyze** — GPT-5.1 Vision scores each image:
   - **Relevance** (0-10) — Match to story details
   - **Verifiability** (0-10) — Source context confirms content
   - **Usability** (0-10) — Resolution, watermarks, cropping
   - **AI Detection** — Flags AI-generated images
6. **Decide** — Approved if Relevance ≥7, Verifiability ≥6, Usability ≥6, NOT AI

**Model:** GPT-5.1 (queries + vision analysis)

**Key Table:** `story_photos`

```bash
python3 -m photo_researcher.main --single --save-output
```

---

### 5. Text Generator (`text_generator/`)

**Purpose:** Generates final text content for Instagram stories.

**Pipeline:**
1. **Story Slides** (7-9 slides) — Built around "Wait, What?" moments
2. **Cover Options** (6 variations) — Viral hook + subtitle + domain tag
3. **Photo Captions** — Documentary-style descriptions for approved photos

**Model:** GPT-5.2

**Key Tables:** `story_generations`, `story_slides`

**Character Limits:**
- 1 paragraph slide: MAX 549 characters
- 2 paragraph slide: MAX 502 characters total

```bash
cd text_generator
python main.py --dry-run --out test_output.md  # Preview
python main.py --story-id <UUID>                # Process specific story
python main.py --random --dry-run --out test.md # Random story for testing
```

---

### 6. Thumbnail Generator (`thumbnail_generator/`)

**Purpose:** Creates AI-generated cover images for Instagram carousel posts.

**Pipeline:**
1. **Concept Generation** — GPT-5.2 creates 3 creative concepts:
   - **Literal** — Documentary-style (specific person/place/object)
   - **Symbolic** — Visual metaphor (abstract representation)
   - **Atmospheric** — Mood-driven (environmental, setting-focused)
2. **Prompt Building** — Full prompts with composition constraints + brand rules
3. **Image Generation** — Nano Banana (Gemini) generates 1080×1350 images
4. **Preview** — Interactive HTML for concept selection

**Models:** GPT-5.2 (concepts), Gemini 2.5 Flash / Gemini 3 Pro (images)

**Image Specs:**
- Dimensions: 1080×1350 (4:5 Instagram aspect ratio)
- Composition: Subjects in upper half, lower 45% reserved for text overlay
- Style: Cinematic, dark, Interstellar × Arrival aesthetic

**Key Table:** `story_thumbnails`

```bash
cd thumbnail_generator
python main.py --test              # Generate + open preview
python main.py --test --pro        # Higher quality (Gemini 3 Pro)
python main.py --story-id <UUID>   # Process specific story
python main.py --select <thumb_id> # Select a thumbnail
```

---

### 7. Pre-Assembler (`pre_assembler/`)

**Purpose:** Web-based tool for visually assembling and reviewing Instagram carousel stories before final rendering.

**Features:**
- Grid dashboard of stories ready for assembly
- Drag-and-drop slide reordering with SortableJS
- Toggle individual slides on/off for final export
- Inline text editing and photo swapping
- Switch between cover title/subtitle variations and thumbnails
- Approval workflow for final assembly

**Tech Stack:** FastAPI, PostgreSQL, Alpine.js, Tailwind CSS

**Key Table:** `story_assemblies`

```bash
cd pre_assembler
uvicorn main:app --reload --port 8000
# Open http://localhost:8000
```

---

### 8. Assembler (`assembler/`)

**Purpose:** Converts approved story assemblies (HTML/CSS) into final PNG image assets for Instagram carousels.

**Pipeline:**
1. **Fetch** — Query stories with `approved_for_assembly=True`
2. **Build** — Inject text, images, and metadata into HTML templates
3. **Render** — Playwright (headless Chromium) captures 1080×1350 screenshots
4. **Finalize** — Update `story_assemblies.status` to `finalized`

**Output:** By default, no local files are written. Set `ASSEMBLER_KEEP_OUTPUT=1` for debugging.

```bash
cd assembler
python main.py  # Process all approved stories
```

---

### 9. Scheduler (`scheduler/`)

**Purpose:** Publishes finalized stories to Instagram via the Graph API.

**Pipeline:**
1. **Select** — Pick one assembled story from the database
2. **Render** — Generate PNG slides using the assembler renderer
3. **Upload** — Store PNGs in Supabase Storage (public URLs)
4. **Publish** — Create Instagram carousel via Graph API

**Note:** This module performs NO database writes—it never marks stories as posted.

**Token Management:** Long-lived tokens with periodic refresh for unattended posting.

```bash
python scheduler/main.py test-post --approved-only
python -m scheduler.main refresh-token  # One-time token exchange
```

---

## 🗄️ Database Schema

The pipeline uses PostgreSQL (Supabase) with the following core tables:

### Data Flow

```
leads                    → story_research        → story_generations    → story_thumbnails
  ↓                           ↓                       ↓                       ↓
discovery_topics         story_photos            story_slides          story_assemblies
  ↓
processed_urls
```

### Key Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `leads` | Raw story candidates | `title`, `url`, `brand_score`, `virality_score`, `status` |
| `discovery_topics` | Search topic queue | `topic`, `status`, `origin_lead_id` |
| `processed_urls` | URL deduplication | `url`, `processed_at` |
| `story_research` | Research packages | `lead_id`, `research_data` (JSONB), `status` |
| `story_photos` | Verified images | `story_research_id`, `image_url`, `relevance_score`, `status` |
| `story_generations` | Generated text | `story_research_id`, `hook_title`, `subtitle`, `domain_tag` |
| `story_slides` | Carousel content | `story_generation_id`, `slide_order`, `text_content`, `document_type_tag` |
| `story_thumbnails` | Cover images | `story_generation_id`, `concept_type`, `image_url`, `is_selected` |
| `story_assemblies` | Carousel assembly | `story_generation_id`, `assembly_data` (JSONB), `status`, `rendered_files` |

### Status Workflows

**leads.status:**
`new` → `approved` → `published` (or `rejected`)

**story_research.status:**
`queued` → `in_progress` → `completed` (or `skipped`)

**story_photos.status:**
`potential` → `approved` / `rejected`

**story_thumbnails.status:**
`pending` → `generating` → `generated` → `approved` / `rejected` (or `failed`)

**story_assemblies.status:**
`new` → `draft` → `finalized`

**story_generations flags:**
`approved_for_assembly` = True → Ready for Assembler to render

---

## 🔧 Environment Setup

### Prerequisites
- Python 3.10+
- PostgreSQL Database (Supabase recommended)
- API Keys: OpenAI, Perplexity, Google (Custom Search + Gemini)

### Environment Variables

Create a `.env` file in the `code/` directory:

```ini
# Database (Supabase/PostgreSQL)
POSTGRES_HOST=your-host.supabase.co
POSTGRES_PORT=6543
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password

# AI Services
OPENAI_API_KEY=sk-...
PERPLEXITY_API_KEY=pplx-...

# Google (Photo Research + Thumbnail Generation)
GOOGLE_CUSTOM_SEARCH_KEY=AIza...
GOOGLE_SEARCH_ENGINE_ID=...
GOOGLE_API_KEY=AIza...  # For Gemini/Nano Banana
```

### Installation

Each module has its own `requirements.txt`. Install per-module or create a shared environment:

```bash
# Per-module (recommended for isolation)
cd lead_generator && pip install -r requirements.txt
cd ../story_researcher && pip install -r requirements.txt
cd ../photo_researcher && pip install -r requirements.txt
cd ../text_generator && pip install -r requirements.txt
cd ../thumbnail_generator && pip install -r requirements.txt

# Or shared environment
pip install openai psycopg2-binary python-dotenv requests typer google-genai
```

---

## 📊 Models & APIs

| Component | Model | Provider | Purpose |
|-----------|-------|----------|---------|
| Lead Generator | gpt-4o / gpt-4o-mini | OpenAI | Filtering, scoring |
| Lead Generator | sonar-pro | Perplexity | Active discovery |
| Lead Generator | text-embedding-3-small | OpenAI | Semantic deduplication |
| Curator | gpt-5.1 | OpenAI | Editorial selection |
| Story Researcher | gpt-4o | OpenAI | Hook identification |
| Story Researcher | sonar-pro | Perplexity | Ground truth research |
| Photo Researcher | gpt-5.1 | OpenAI | Query generation + Vision analysis |
| Text Generator | gpt-5.2 | OpenAI | Story + cover + captions |
| Thumbnail Generator | gpt-5.2 | OpenAI | Concept generation |
| Thumbnail Generator | gemini-2.5-flash-image | Google | Image generation |
| Thumbnail Generator | gemini-3-pro-image-preview | Google | Image generation (Pro) |

---

## 🚀 Typical Workflow

### Weekly Content Cycle

```bash
# 1. Generate new leads (run daily or as cron)
cd lead_generator && python main.py run

# 2. Curate weekly selection
cd ../curator && python main.py

# 3. Research approved stories
cd ../story_researcher
PYTHONPATH=.. python -m story_researcher.main

# 4. Find photos for researched stories
cd ../photo_researcher
python3 -m photo_researcher.main --limit 10

# 5. Generate text content
cd ../text_generator && python main.py

# 6. Create cover images
cd ../thumbnail_generator
python main.py --test  # Review and select

# 7. Assemble carousel (web UI)
cd ../pre_assembler
uvicorn main:app --port 8000  # Open http://localhost:8000

# 8. Render final PNGs (after approval in UI)
cd ../assembler && python main.py

# 9. Publish to Instagram
cd ../scheduler
python main.py test-post --approved-only
```

### Testing a Single Story

```bash
# Research one story with detailed output
PYTHONPATH=code ./story_researcher/venv/bin/python -m story_researcher.main --single

# Generate text with preview
python text_generator/main.py --random --dry-run --out test.md

# Generate thumbnails with interactive preview
python thumbnail_generator/main.py --test --story-id <UUID>
```

---

## 📁 Project Structure

```
code/
├── README.md                   # This file
├── brand-guide2.md             # Brand guidelines (system prompt)
├── .env                        # Environment variables
│
├── lead_generator/             # Discovery & filtering
│   ├── main.py
│   ├── logic/
│   │   ├── workflow.py
│   │   └── filters.py          # AI prompts for filtering
│   └── services/
│       ├── rss.py              # Feed list
│       ├── perplexity.py
│       └── llm.py
│
├── curator/                    # Editorial selection
│   ├── main.py
│   ├── logic.py
│   └── db.py
│
├── story_researcher/           # Research pipeline
│   ├── main.py
│   ├── researcher.py
│   └── prompts.py
│
├── photo_researcher/           # Image curation
│   ├── main.py
│   ├── generator.py            # Query generation
│   ├── searcher.py             # Google Images
│   ├── scraper.py              # Page context
│   ├── analyzer.py             # GPT Vision
│   └── validator.py
│
├── text_generator/             # Content writing
│   ├── main.py
│   └── generator.py            # Prompts for slides/covers/captions
│
├── thumbnail_generator/        # Cover art
│   ├── main.py
│   ├── prompt_generator.py     # GPT concept generation
│   ├── prompt_builder.py       # Prompt assembly
│   ├── nanobanana.py           # Gemini API client
│   └── preview.py              # HTML preview generator
│
├── pre_assembler/              # Carousel assembly editor
│   ├── main.py                 # FastAPI app
│   ├── db.py                   # Database queries
│   ├── models.py               # Pydantic models
│   └── static/                 # Frontend (Alpine.js + Tailwind)
│
├── assembler/                  # PNG rendering
│   ├── main.py                 # Batch processor
│   ├── builder.py              # HTML injection
│   ├── renderer.py             # Playwright screenshots
│   └── db_utils.py
│
├── scheduler/                  # Instagram publishing
│   ├── main.py                 # CLI orchestrator
│   ├── instagram.py            # Graph API client
│   ├── storage.py              # Supabase upload
│   └── token_store.py          # Token management
│
└── template_design/            # Visual assets
    ├── all_templates/
    ├── chosen_templates/
    └── img/
```

---

## 🎨 Visual Identity

### Aesthetic
**Interstellar × Arrival × Scientific Mystery × Calm Esoteric Intelligence**

- Dark or deep-toned backgrounds (navy, charcoal, deep space)
- Minimalistic, poster-like clarity
- Soft gradients and gentle glows
- Technical textures (grids, diagrams, telemetry, star maps)
- Wide negative space

### Avoid
- Neon cyberpunk clichés
- Chaotic occult symbolism
- Gore or shock imagery
- Meme aesthetics
- Overly busy compositions

---

## 📚 Additional Documentation

Each module contains its own detailed README:

- [`lead_generator/README.md`](lead_generator/README.md) — Discovery & filtering details
- [`curator/README.md`](curator/README.md) — Editorial selection process
- [`story_researcher/README.md`](story_researcher/README.md) — Research phases
- [`photo_researcher/README.md`](photo_researcher/README.md) — Image verification pipeline
- [`text_generator/README.md`](text_generator/README.md) — Content generation
- [`thumbnail_generator/README.md`](thumbnail_generator/README.md) — Cover art creation
- [`pre_assembler/README.md`](pre_assembler/README.md) — Carousel assembly editor
- [`assembler/README.md`](assembler/README.md) — PNG rendering pipeline
- [`scheduler/README.md`](scheduler/README.md) — Instagram publishing

---

## 📝 License

Internal project — TheBoldUnknown
