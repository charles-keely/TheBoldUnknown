# Thumbnail Generator

AI-generated cover images for TheBoldUnknown Instagram carousel posts.

## Overview

This module takes completed story generations (with hook_title, subtitle, domain_tag) and produces 3 AI-generated cover image variations using:

1. **GPT-5.2** - Generates creative concepts based on story content
2. **Nano Banana (Google Gemini)** - Generates the actual images

## Architecture

```
story_generations (title, subtitle, domain)
        ↓
   prompt_generator.py (GPT-5.2)
   → 3 creative concepts (literal, symbolic, atmospheric)
        ↓
   prompt_builder.py
   → Full prompts with constraints + brand rules
        ↓
   nanobanana.py (Gemini Image API)
   → 3 generated images (1080x1350)
        ↓
   story_thumbnails (database)
```

## Installation

```bash
cd thumbnail_generator
pip install -r requirements.txt
```

## Environment Variables

Required in `.env`:

```
OPENAI_API_KEY=sk-...          # For GPT-5.2 prompt generation
GOOGLE_API_KEY=AIza...         # For Nano Banana (Gemini) image generation
POSTGRES_HOST=...
POSTGRES_PORT=6543
POSTGRES_DB=postgres
POSTGRES_USER=...
POSTGRES_PASSWORD=...
```

## Database Setup

Run this SQL in Supabase:

```sql
CREATE TABLE public.story_thumbnails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_generation_id UUID REFERENCES story_generations(id),
    concept_number INTEGER CHECK (concept_number BETWEEN 1 AND 3),
    concept_type TEXT CHECK (concept_type IN ('literal', 'symbolic', 'atmospheric')),
    scene_description TEXT,
    full_prompt TEXT,
    image_url TEXT,
    status TEXT CHECK (status IN ('pending', 'generating', 'generated', 'approved', 'rejected', 'failed')),
    is_selected BOOLEAN DEFAULT FALSE,
    generation_metadata JSONB,
    created_at TIMESTAMP DEFAULT now(),
    generated_at TIMESTAMP,
    selected_at TIMESTAMP
);
```

## Usage

### 🧪 Test Mode (Recommended for First Run)

Generate thumbnails for one story and open an interactive HTML preview:

```bash
# Test with a random story
python main.py --test

# Test with a specific story
python main.py --test --story-id <generation_id>

# Test with Pro model (higher quality)
python main.py --test --pro

# Don't auto-open browser
python main.py --test --no-browser
```

The preview page lets you:
- Switch between the 3 generated concepts with buttons
- Use keyboard shortcuts (1, 2, 3 or arrow keys)
- See the full cover template with your title/subtitle overlaid
- Compare how each concept fits the layout

### Process all pending stories

```bash
python main.py
```

### Process a specific story

```bash
python main.py --story-id <generation_id>
```

### Use Nano Banana Pro (higher quality)

```bash
python main.py --pro
```

### Limit number of stories

```bash
python main.py --limit 5
```

### Select a thumbnail

```bash
python main.py --select <thumbnail_id>
```

### Full options

```bash
python main.py --help
```

## Concept Types

Each story gets 3 different thumbnail concepts:

1. **Literal** - Documentary-style: specific person, place, or object from the story
2. **Symbolic** - Visual metaphor: abstract representation of the concept
3. **Atmospheric** - Mood-driven: environmental, setting-focused

## Image Specifications

- **Dimensions**: 1080×1350 (4:5 aspect ratio for Instagram)
- **Composition**: Subjects in upper half, lower 45% reserved for text overlay
- **Style**: Cinematic, dark, Interstellar × Arrival aesthetic
- **Restrictions**: No text, logos, or watermarks in generated images

## File Structure

```
thumbnail_generator/
├── __init__.py          # Module exports
├── config.py            # Configuration and constants
├── db.py                # Database operations
├── main.py              # CLI orchestrator
├── nanobanana.py        # Gemini image generation client
├── prompt_builder.py    # Assembles prompts with constraints
├── prompt_generator.py  # GPT-5.2 concept generation
├── requirements.txt     # Dependencies
├── schema.sql           # Database schema
├── PLAN.md             # Implementation plan
├── README.md           # This file
└── output/             # Generated images (local)
```

## Models Used

| Task | Model | Provider |
|------|-------|----------|
| Concept Generation | gpt-5.2 | OpenAI |
| Image Generation | gemini-2.5-flash-image | Google |
| Image Generation (Pro) | gemini-3-pro-image-preview | Google |

## API Costs

- **GPT-5.2**: ~$0.01 per story (3 concepts)
- **Nano Banana**: ~$0.02 per image
- **Total**: ~$0.07 per story (3 images)

## Output

### Generated Images
- Local: `thumbnail_generator/output/`
- Database: `story_thumbnails.image_url` (local path)
- Naming: `{title}_{timestamp}_c{1|2|3}.png`

### Test Preview
- Latest: `thumbnail_generator/output/test_preview.html`
- Timestamped: `thumbnail_generator/output/test_preview_{timestamp}.html`

The preview HTML uses the actual cover3.html template styling with:
- Your hook_title and subtitle displayed
- Domain tag in the metadata position
- Logo and footer elements from template_design/img/
- Interactive buttons to switch between concepts
- Keyboard navigation (1/2/3 keys or arrows)

For production, you may want to upload images to cloud storage and update the URLs.
