# Pipeline Manager

A unified web UI to orchestrate the entire content pipeline from lead generation through thumbnail generation.

## Overview

The Pipeline Manager provides visibility and control over the full content journey:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Pipeline Manager Scope                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│   │    LEADS     │ ─▶ │   CURATION   │ ─▶ │   RESEARCH   │              │
│   │  (Discovery) │    │  (Selection) │    │              │              │
│   └──────────────┘    └──────────────┘    └──────────────┘              │
│                                                   │                      │
│           ┌───────────────────────────────────────┘                      │
│           │                                                              │
│           ▼                                                              │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│   │     TEXT     │ ─▶ │    PHOTOS    │ ─▶ │  THUMBNAILS  │              │
│   │  (Writing)   │    │   (Visuals)  │    │  (Cover Art) │              │
│   └──────────────┘    └──────────────┘    └──────────────┘              │
│                                                   │                      │
└───────────────────────────────────────────────────┼──────────────────────┘
                                                    │
                                                    ▼
                         ┌──────────────────────────────────────────────┐
                         │              Existing Web Apps               │
                         │  ┌─────────────┐    ┌─────────────┐         │
                         │  │PRE-ASSEMBLER│ ─▶ │  SCHEDULER  │         │
                         │  │  (Layout)   │    │ (Publisher) │         │
                         │  └─────────────┘    └─────────────┘         │
                         └──────────────────────────────────────────────┘
```

## Features

### Two Operating Modes

1. **Auto Mode** - Run the entire pipeline automatically from lead generation through thumbnail generation with minimal intervention.

2. **Step Mode** - Run each phase individually with user confirmation required between phases. Perfect for quality control and debugging.

### Key Capabilities

- **Real-time Progress Tracking** - Live updates via Server-Sent Events (SSE)
- **Session Recovery** - All state persisted to database; resume where you left off
- **Phase Navigation** - Jump between phases to review results at any time
- **Cancellation with Cleanup** - Cancel runs and optionally delete all created data
- **Run History** - View results from any past run

## Quick Start

### 1. Install Dependencies

```bash
cd pipeline_manager
pip install -r requirements.txt
```

### 2. Initialize Database

The schema is auto-initialized on first run, or you can run manually:

```bash
psql $DATABASE_URL -f schema.sql
```

### 3. Start the Server

```bash
# Development
uvicorn main:app --reload --port 8001

# Production
uvicorn main:app --host 0.0.0.0 --port 8001
```

### 4. Access the UI

- **Pipeline Manager**: http://localhost:8001
- **Pre-Assembler**: http://localhost:8000 (existing app)

## API Endpoints

### Session & Active Run

```
GET  /api/pipeline/active              # Check for active run
```

### Pipeline Management

```
POST /api/pipeline/start               # Start new pipeline
GET  /api/pipeline/runs                # List runs (paginated)
GET  /api/pipeline/runs/{id}           # Get run details
POST /api/pipeline/runs/{id}/pause     # Pause running pipeline
POST /api/pipeline/runs/{id}/resume    # Resume paused pipeline
POST /api/pipeline/runs/{id}/cancel    # Cancel pipeline
```

### Phase Control (Step Mode)

```
POST /api/pipeline/runs/{id}/phase/{phase}/start   # Start phase
POST /api/pipeline/runs/{id}/phase/{phase}/retry   # Retry failed phase
POST /api/pipeline/runs/{id}/phase/{phase}/skip    # Skip phase
POST /api/pipeline/runs/{id}/phase/{phase}/approve # Approve results
```

### Real-time Updates

```
GET  /api/pipeline/runs/{id}/stream    # SSE stream for progress
```

### Phase Results

```
GET  /api/pipeline/runs/{id}/phases/1/leads      # Lead results
GET  /api/pipeline/runs/{id}/phases/2/research   # Research results
GET  /api/pipeline/runs/{id}/phases/3/text       # Text gen results
GET  /api/pipeline/runs/{id}/phases/4/photos     # Photo results
GET  /api/pipeline/runs/{id}/phases/5/thumbnails # Thumbnail results
```

## Architecture

```
pipeline_manager/
├── __init__.py           # Package init
├── main.py               # FastAPI application
├── config.py             # Configuration
├── models.py             # Pydantic models
├── db.py                 # Database operations
├── executor.py           # Pipeline orchestration
├── workers/              # Phase worker adapters
│   ├── lead_generator.py
│   ├── curator.py
│   ├── story_researcher.py
│   ├── text_generator.py
│   ├── photo_researcher.py
│   └── thumbnail_generator.py
├── static/
│   ├── index.html        # Dashboard UI
│   └── pipeline.html     # Pipeline view UI
├── schema.sql            # Database schema
└── requirements.txt
```

## Environment Variables

```env
# Pipeline Manager
PIPELINE_HOST=0.0.0.0
PIPELINE_PORT=8001

# Database (uses existing .env)
POSTGRES_HOST=...
POSTGRES_PORT=5432
POSTGRES_DB=...
POSTGRES_USER=...
POSTGRES_PASSWORD=...

# Or use DATABASE_URL
DATABASE_URL=postgresql://...
```

## Integration with Existing Apps

The Pipeline Manager wraps existing modules as worker adapters:

- `lead_generator/` - Lead discovery workflow
- `curator/` - Story curation logic
- `story_researcher/` - Research via Perplexity + GPT
- `text_generator/` - Slide/cover/caption generation
- `photo_researcher/` - Google Image search + analysis
- `thumbnail_generator/` - AI cover image generation

When a pipeline completes, stories are ready for the **Pre-Assembler** at http://localhost:8000.

