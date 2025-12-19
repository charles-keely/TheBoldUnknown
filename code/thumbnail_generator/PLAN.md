# Thumbnail Generator Implementation Plan

## Overview

The `thumbnail_generator` module produces AI-generated cover images for Instagram carousel posts using **Nano Banana** (image generation API). It takes completed `story_generations` (containing hook_title, subtitle, domain_tag) and story research, then generates 3 creative thumbnail variations that fit the editorial template layout.

## Architecture

```
story_generations (hook_title, subtitle, domain_tag)
        ↓
   story_research (research_data for context)
        ↓
   ┌─────────────────────────────────────┐
   │       PROMPT GENERATOR (GPT-5.2)     │
   │  - Analyzes story content            │
   │  - Creates 3 creative scene concepts │
   │  - Outputs JSON with scene details   │
   └─────────────────────────────────────┘
        ↓
   ┌─────────────────────────────────────┐
   │       PROMPT BUILDER                 │
   │  - Combines creative concepts with   │
   │  - Static dimensional constraints    │
   │  - Brand aesthetic rules             │
   └─────────────────────────────────────┘
        ↓
   ┌─────────────────────────────────────┐
   │       NANO BANANA API                │
   │  - Generates 1080x1350 images        │
   │  - Returns image URLs                │
   └─────────────────────────────────────┘
        ↓
   story_thumbnails (stored in DB)
```

## Core Principles

1. **Template-Aware**: Images must respect the editorial layout with proper safe zones
2. **Brand-Aligned**: Aesthetic must match "Interstellar × Arrival × Scientific Mystery × Calm Esoteric Intelligence"
3. **Story-Driven**: Creative direction comes from the actual story content
4. **Model**: Use `gpt-5.2` for prompt generation

---

## 1. Template Layout Analysis

Based on `cover3.html`, the cover image has these overlay elements:

```
┌──────────────────────────────────────┐
│ [LOGO]              [META TAG]       │  ← Top 10%: Logo + Metadata
│  90px                ~70px height    │
│                                      │
│                                      │  ← Upper half: SAFE FOR SUBJECTS
│         (Subject Area)               │
│                                      │
│                                      │
├──────────────────────────────────────┤
│                                      │  ← Lower 45%: TEXT ZONE
│         MAIN TITLE                   │     (avoid focal objects)
│         100px font                   │
│                                      │
│         Subtitle text                │
│         ~24px font                   │
│                                      │
│ [01/08]                    [→]       │  ← Footer: Pagination + Arrow
└──────────────────────────────────────┘

Dimensions: 1080 × 1350 (vertical)
Margin: 70px all sides
```

### Safe Zone Map

| Zone | Position | Content | Image Constraint |
|------|----------|---------|------------------|
| Top-Left | 70px from edges | Logo (90px) | Keep visually calm |
| Top-Right | 70px from edges | Metadata label | Minimal detail |
| Center-Lower | 50-100% height | Title + Subtitle | **NO focal subjects** |
| Footer | Bottom 70px | Pagination, Arrow | No detail needed |
| Upper Half | 0-55% height | **SUBJECT AREA** | Place main subjects here |

---

## 2. Dimensional Constraints (Static Block)

This block is appended to EVERY Nano Banana prompt:

```
IMAGE FORMAT AND COMPOSITION CONSTRAINTS:

• Canvas size: 1080 × 1350 pixels (vertical editorial layout).
• Subject placement: Keep all major subjects positioned in the upper half or upper-right third of the frame.
• Lower safe zone: Avoid placing faces, focal objects, or high-contrast details in the lower 45% of the image.
• Center-lower region: Maintain clean negative space for large headline typography.
• Top-left corner: Keep visually calm for a circular logo overlay (90px diameter).
• Top-right corner: Keep minimally detailed for a small metadata label.
• Background style: Cinematic, grounded, and editorial — not busy or cluttered.
• Lighting: Should guide the eye away from text-safe zones and toward the subject.
• Restrictions: NO text, NO logos, NO watermarks, NO UI elements, NO embedded typography.
```

---

## 3. Brand Aesthetic Rules (Static Block)

Derived from `brand-guide2.md`:

```
VISUAL AESTHETIC (TheBoldUnknown Brand):

• Style: Interstellar × Arrival × Scientific Mystery × Calm Esoteric Intelligence
• Backgrounds: Dark or deep-toned (navy, charcoal, deep space, shadows)
• Composition: Minimalistic, poster-like clarity, wide negative space
• Atmosphere: Soft gradients, gentle glows, subtle atmosphere
• Textures: Technical elements welcome (grids, diagrams, telemetry, star maps, architectural drawings)
• Mood: Quietly strange, grounded, rational, cinematic
• Lighting: Dramatic but natural, never harsh or neon

AVOID:
• Neon cyberpunk clichés
• Chaotic occult symbolism
• Gore or shock imagery
• Meme aesthetics
• Cartoon or comic book styles
• Overly busy compositions
• Cluttered backgrounds
```

---

## 4. Prompt Generator (GPT-5.2)

### Inputs
- `hook_title`: The main title (e.g., "WHY DOES DÉJÀ VU FEEL REAL?")
- `subtitle`: Context sentence
- `domain_tag`: Topic category (e.g., "Consciousness Studies")
- `research_data`: Full research context from story_research

### Process

GPT-5.2 generates **3 distinct creative concepts** for the thumbnail. Each concept includes:

1. **Scene Description**: What the image depicts (subject, setting, mood)
2. **Subject Placement**: Where in frame (e.g., "upper-right third, looking away")
3. **Key Visual Elements**: Specific objects, textures, atmospheric effects
4. **Color Palette**: Dominant tones that match the story mood
5. **Lighting Direction**: How light emphasizes the subject

### Output Format (JSON)

```json
{
    "concepts": [
        {
            "id": 1,
            "scene_description": "A silhouetted figure stands before a massive neural network visualization, connections pulsing with soft blue light",
            "subject_placement": "Upper-right third, figure in profile facing left",
            "key_elements": ["neural pathways", "soft pulse effects", "depth of field blur"],
            "color_palette": ["deep navy", "electric blue", "soft white glow"],
            "lighting": "Backlit by the visualization, creating rim lighting on the figure",
            "reasoning": "Represents the internal mystery of déjà vu as a neural phenomenon"
        },
        {
            "id": 2,
            "scene_description": "...",
            ...
        },
        {
            "id": 3,
            "scene_description": "...",
            ...
        }
    ]
}
```

### Prompt Template for GPT-5.2

```
You are creating visual concepts for TheBoldUnknown Instagram cover images.

STORY CONTEXT:
Title: {hook_title}
Subtitle: {subtitle}
Domain: {domain_tag}

Research Summary:
{research_summary}

---

YOUR TASK:
Generate 3 distinct creative concepts for a thumbnail image that:
1. Visually represents the core theme/mystery of this story
2. Creates immediate intrigue and curiosity
3. Works as a "movie poster" that makes someone want to read the story

COMPOSITION REQUIREMENT:
The image will have text overlaid on the lower 45%. All subjects must be positioned in the UPPER HALF of the frame.

AESTHETIC:
- Cinematic, atmospheric, documentary-style
- Dark/moody backgrounds with selective lighting
- Technical or scientific undertones when appropriate
- Mysterious but grounded (never supernatural or horror)

Each concept should take a DIFFERENT visual approach:
- Concept 1: Literal/Documentary (if there's a specific person, place, or object)
- Concept 2: Symbolic/Abstract (visual metaphor for the concept)
- Concept 3: Environmental/Atmospheric (mood-driven, setting-focused)

OUTPUT: JSON with 3 concepts, each containing scene_description, subject_placement, key_elements, color_palette, lighting, and reasoning.
```

---

## 5. Prompt Builder

Combines:
1. Creative concept from GPT-5.2
2. Static dimensional constraints
3. Static brand aesthetic rules

### Final Prompt Structure

```
{creative_scene_description}

SUBJECT FRAMING:
{subject_placement}
Rule-of-thirds composition. Avoid dead-center placement.
Subject should feel observed, candid, or documentary in tone.

KEY VISUAL ELEMENTS:
{key_elements_formatted}

COLOR PALETTE:
{color_palette_formatted}

LIGHTING:
{lighting_description}

---

{DIMENSIONAL_CONSTRAINTS_BLOCK}

---

{BRAND_AESTHETIC_BLOCK}
```

---

## 6. Nano Banana Integration (Google Gemini)

**Nano Banana** is actually Google's Gemini Image Generation API:
- `gemini-2.5-flash-image` = Nano Banana (fast, 1K resolution)
- `gemini-3-pro-image-preview` = Nano Banana Pro (advanced, up to 4K)

### API Implementation

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=GOOGLE_API_KEY)

response = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents=[prompt],
    config=types.GenerateContentConfig(
        response_modalities=['IMAGE'],
        image_config=types.ImageConfig(
            aspect_ratio="4:5",  # 1080x1350 = 4:5
        )
    )
)

for part in response.parts:
    if part.inline_data is not None:
        image = part.as_image()
        image.save("thumbnail.png")
```

### Aspect Ratio for Instagram Cover

Our target is 1080×1350 which equals **4:5** aspect ratio.

Gemini 2.5 Flash generates **896×1152** for 4:5 (can be upscaled if needed).
Gemini 3 Pro can generate up to **3712×4608** at 4K.

### Process
1. Build 3 final prompts (one per concept)
2. Call Gemini API 3 times
3. Save images locally and store paths in database

---

## 7. Database Schema

### New Table: `story_thumbnails`

```sql
CREATE TABLE IF NOT EXISTS public.story_thumbnails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_generation_id UUID NOT NULL REFERENCES public.story_generations(id),
    
    -- Concept metadata
    concept_number INTEGER NOT NULL CHECK (concept_number BETWEEN 1 AND 3),
    concept_type TEXT, -- 'literal', 'symbolic', 'atmospheric'
    scene_description TEXT,
    
    -- Generated content
    full_prompt TEXT NOT NULL,
    image_url TEXT,
    
    -- Status tracking
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'generated', 'approved', 'rejected')),
    
    -- Selection
    is_selected BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    generation_metadata JSONB, -- Full concept details, API response, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    generated_at TIMESTAMP WITH TIME ZONE
);

-- Index for fast lookups
CREATE INDEX idx_story_thumbnails_generation ON story_thumbnails(story_generation_id);
CREATE INDEX idx_story_thumbnails_status ON story_thumbnails(status);

-- Ensure only one selected thumbnail per story
CREATE UNIQUE INDEX idx_story_thumbnails_selected 
ON story_thumbnails(story_generation_id) 
WHERE is_selected = TRUE;
```

---

## 8. Module Structure

```
thumbnail_generator/
├── __init__.py
├── config.py          # API keys, model config, constants
├── db.py              # Database operations
├── prompt_generator.py # GPT-5.2 creative concept generation
├── prompt_builder.py   # Assembles final prompts with constraints
├── nanobanana.py       # Nano Banana API client
├── main.py             # Orchestrator
├── PLAN.md             # This file
├── README.md           # Usage documentation
├── requirements.txt    # Dependencies
└── schema.sql          # Database schema
```

---

## 9. Implementation Steps

### Phase 1: Foundation
1. [x] Create PLAN.md (this document)
2. [ ] Create database schema (`schema.sql`)
3. [ ] Create `config.py` with constants
4. [ ] Create `db.py` with database operations

### Phase 2: Prompt Generation
5. [ ] Implement `prompt_generator.py` (GPT-5.2 concept generation)
6. [ ] Implement `prompt_builder.py` (assemble final prompts)
7. [ ] Test prompt quality with sample stories

### Phase 3: Image Generation
8. [ ] Implement `nanobanana.py` (API client)
9. [ ] Integrate with prompt builder
10. [ ] Test end-to-end generation

### Phase 4: Orchestration
11. [ ] Implement `main.py` orchestrator
12. [ ] Add selection/approval workflow
13. [ ] Create README.md

---

## 10. Flow Diagram

```
1. FETCH: Get story_generation that needs thumbnails
   ↓
2. CONTEXT: Load associated story_research data
   ↓
3. GENERATE CONCEPTS: GPT-5.2 creates 3 creative concepts
   ↓
4. BUILD PROMPTS: Combine concepts + constraints + brand rules
   ↓
5. GENERATE IMAGES: Call Nano Banana API (3x)
   ↓
6. STORE: Save to story_thumbnails table
   ↓
7. SELECT: Mark one as selected (manual or auto)
```

---

## 11. API Keys Required

| Service | Environment Variable | Purpose |
|---------|---------------------|---------|
| OpenAI | `OPENAI_API_KEY` | GPT-5.2 for prompt generation |
| Google | `GOOGLE_API_KEY` | Nano Banana (Gemini) for image generation |

---

## 12. Example Workflow

### Input Story

```
Title: "WHY DOES DÉJÀ VU FEEL REAL?"
Subtitle: "These classified CIA documents may hold the secrets to the phenomenon of déjà vu."
Domain: "Consciousness Studies"
Research: [Full perplexity research about déjà vu, CIA documents, etc.]
```

### Generated Concepts

**Concept 1 (Literal):**
> A shadowy figure examines a redacted CIA document under harsh desk lamp light. The document is partially visible, showing "CLASSIFIED" stamps. Shot from above, figure in upper portion.

**Concept 2 (Symbolic):**
> A human silhouette overlaid with two identical mirrored moments—same scene, same position, infinite loop feeling. Deep blue tones, soft glow at edges.

**Concept 3 (Atmospheric):**
> An empty hospital corridor stretches into fog, fluorescent lights creating an endless tunnel effect. Shot in cool desaturated tones with selective focus.

### Final Prompt (Concept 2)

```
A human silhouette overlaid with two identical mirrored moments—same scene, same position, creating an infinite loop feeling. The figure appears contemplative, caught in the space between memory and present.

SUBJECT FRAMING:
Centered silhouette in upper-third of frame, with mirror effect extending downward but fading before the lower portion.
Rule-of-thirds composition. Subject should feel observed, caught in a moment of recognition.

KEY VISUAL ELEMENTS:
- Double-exposure effect
- Soft edge blur between layers
- Subtle neural pathway textures
- Depth creating infinite regression

COLOR PALETTE:
- Deep navy blue
- Soft electric blue glow
- Warm amber accent (memory tone)
- Rich blacks in shadows

LIGHTING:
Backlit figure with soft rim light. Mirror layers have decreasing brightness creating depth.

---

IMAGE FORMAT AND COMPOSITION CONSTRAINTS:
• Canvas size: 1080 × 1350 pixels (vertical editorial layout).
• Subject placement: Keep all major subjects positioned in the upper half or upper-right third of the frame.
[... full constraint block ...]

---

VISUAL AESTHETIC (TheBoldUnknown Brand):
• Style: Interstellar × Arrival × Scientific Mystery × Calm Esoteric Intelligence
[... full aesthetic block ...]
```

---

## 13. Future Enhancements

- **A/B Testing**: Track which concept types perform best
- **Auto-Selection**: Use GPT-5.2 vision to judge generated images against criteria
- **Regeneration**: If image doesn't meet quality threshold, regenerate with refined prompt
- **Batch Processing**: Process multiple stories in parallel

---

## 14. Dependencies

```
openai>=1.0.0
google-genai>=1.0.0
psycopg2-binary>=2.9.0
python-dotenv>=1.0.0
Pillow>=10.0.0
```

---

## Notes

- The dimensional constraints are designed to work with the `cover3.html` template specifically
- If template changes, update the safe zone specifications in Section 2
- Nano Banana API details (endpoint, auth, params) need to be confirmed and added to `nanobanana.py`
