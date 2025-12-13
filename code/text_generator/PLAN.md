# Text Generator Implementation Plan

## Overview
The `text_generator` module produces all textual content for Instagram posts. It transforms raw research (`story_research`) and approved photos (`story_photos`) into viral-ready, brand-aligned social media copy using **GPT-5.2**.

## core Principles
- **Viral-First**: Titles and hooks must be designed to stop the scroll.
- **Brand-Aligned**: All tags must be single words or short phrases. Tone must match `brand-guide2.md`.
- **Data-Driven**: Content is strictly based on the Perplexity research context.
- **Model**: Exclusively use `gpt-5.2`.

## 1. Cover Image Generation
**Goal**: Create the "Hook" that draws the user in.

### Inputs
- Research Summary from `story_research`.
- Brand Guidelines.

### Process
1.  **Generation**: Prompt GPT-5.2 to generate **3 distinct options**. Each option contains:
    -   **Title/Hook**: All caps. High virality. (e.g., "WHY DOES DEJA VU FEEL REAL?")
    -   **Subtitle**: ~1 sentence context. (e.g., "These classified documents may hold the secrets...")
    -   **Subject/Domain Tag**: Short phrase (e.g., "Consciousness").
2.  **Selection (Judge)**:
    -   Prompt GPT-5.2 to evaluate the 3 options based on "virality potential".
    -   Select the winner.
3.  **Storage**:
    -   Store the **Winner** in main columns.
    -   Store **All 3 pairs** in a JSONB column (`generation_metadata`) for future A/B testing or swapping.

## 2. Story Content Generation
**Goal**: Tell the story in a carousel format (Textual Slides).

### Inputs
- Research Summary.
- Selected Title (for context).

### Process
1.  **Prompting**: Single prompt to generate the entire story structure.
2.  **Output Format**: JSON array of slides.
3.  **Constraints**:
    -   **Max Slides**: 15 (Absolute maximum).
    -   **Efficiency**: Use only as many slides as needed to tell the story effectively.
    -   **Content per Slide**: 1-2 paragraphs.
    -   **Character Limits** (Strict):
        -   1 Paragraph: Max **549** chars.
        -   2 Paragraphs: Max **502** chars.
    -   **Tags**: Each slide gets a "Document Type/Interpretive Mode" tag (e.g., "CLASSIFIED ANALYSIS", "FIELD REPORT", "THEORY OVERVIEW").

## 3. Photo Text Generation
**Goal**: Contextualize the visual elements.

### Inputs
- Approved photos from `story_photos` (Description/Metadata).

### Process
For each approved photo, generate:
1.  **Caption**: Explains who/what/where is in the photo.
2.  **Source**: "Source: [Source Name]".
3.  **Concept Tag**: A specific Concept/Mechanism/Angle tag answering "what specific idea does this photo visualize?".

## Data Model (Schema)

### New Table: `story_generations`
Stores the high-level story text (Cover) and the "Judge" results.
```sql
CREATE TABLE IF NOT EXISTS public.story_generations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_research_id UUID NOT NULL REFERENCES public.story_research(id),
    
    -- Winner Content
    hook_title TEXT NOT NULL,
    subtitle TEXT NOT NULL,
    domain_tag TEXT NOT NULL,
    
    -- All generated options (for fallback/swapping)
    -- Structure: [{title, subtitle, tag, score, reasoning}, ...]
    generation_metadata JSONB,
    
    model_used TEXT DEFAULT 'gpt-5.2',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### New Table: `story_slides`
Stores the ordered text slides.
```sql
CREATE TABLE IF NOT EXISTS public.story_slides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_generation_id UUID NOT NULL REFERENCES public.story_generations(id),
    
    slide_order INTEGER NOT NULL,
    text_content TEXT NOT NULL,
    document_type_tag TEXT NOT NULL,
    paragraph_count INTEGER, -- Helper to track 1 vs 2 paragraphs
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Updates to `story_photos`
Store the generated text for photos.
```sql
ALTER TABLE public.story_photos 
ADD COLUMN IF NOT EXISTS caption TEXT,
ADD COLUMN IF NOT EXISTS source_attribution TEXT,
ADD COLUMN IF NOT EXISTS concept_tag TEXT,
ADD COLUMN IF NOT EXISTS text_generated_at TIMESTAMP WITH TIME ZONE;
```

## Implementation Steps

1.  **Database Setup**: Run the schema updates.
2.  **DB Layer (`db.py`)**: 
    -   Function to fetch `completed` research.
    -   Function to save generations.
3.  **Generator Logic (`generator.py`)**:
    -   Implement `CoverGenerator` class (Prompting + Judging).
    -   Implement `StoryGenerator` class (JSON handling + Char limit validation).
    -   Implement `PhotoTextGenerator` class.
4.  **Main Loop (`main.py`)**:
    -   Orchestrate the flow: Research -> Cover -> Story -> Photos.

## Prompt Engineering Strategy (GPT-5.2)

- **Cover Prompt**: "Generate 3 viral hooks... output JSON... Judge them."
- **Story Prompt**: "Write a compelling story based on this research... Format as JSON slides... Strict char limits..."
- **Photo Prompt**: "Analyze this photo description... Output Caption, Source, Tag..."
