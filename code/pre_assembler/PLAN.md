# Pre-Assembler — Comprehensive Implementation Plan

## Overview

The Pre-Assembler is a web-based tool that allows visual assembly, editing, and organization of Instagram carousel posts before final rendering. It bridges the content generation pipeline with the final HTML-to-PNG conversion step.

**Core Purpose:** Preview and finalize story content in their actual HTML templates, arranged in Instagram-feed style, with full editing and reordering capabilities.

---

## User Experience Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PRE-ASSEMBLER UX FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌────────────────────┐                                                    │
│   │   STORY DASHBOARD  │  ← All stories with complete content               │
│   │     (index.html)   │  ← Grid of story cards                             │
│   └─────────┬──────────┘                                                    │
│             │                                                                │
│             │  Click on a story card                                         │
│             ▼                                                                │
│   ┌────────────────────┐                                                    │
│   │  ASSEMBLY EDITOR   │  ← Instagram feed-style vertical scroll            │
│   │   (editor.html)    │  ← Full template preview with all content          │
│   │                    │                                                    │
│   │   Features:        │                                                    │
│   │   • Drag & drop    │                                                    │
│   │   • Toggle slides  │                                                    │
│   │   • Edit text      │                                                    │
│   │   • Swap images    │                                                    │
│   │   • Change cover   │                                                    │
│   └────────────────────┘                                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Feature Requirements

### 1. Story Dashboard (index.html)

**Purpose:** Display all stories ready for assembly.

**Ready for Assembly Criteria:**
- `story_research.status = 'completed'`
- Has at least 1 `story_generation` record
- Has at least 1 `story_slide` record
- Has at least 1 `story_photo` with `status = 'approved'`
- Has at least 1 `story_thumbnail` with `status IN ('generated', 'approved')`
- Does NOT have a `story_assemblies` record with `status = 'finalized'`

**UI Elements:**
- Clean grid of story cards (Apple-style: rounded corners, subtle shadows, smooth hover states)
- Each card shows:
  - Story title (hook_title)
  - Subtitle preview
  - Thumbnail preview
  - Domain tag badge
  - Number of slides
  - Number of approved photos
  - Last modified date
  - Status badge (Draft / In Progress / Ready to Export)
- Search/filter functionality (optional for v1)
- "Start Assembly" CTA button

**Aesthetics (Apple Design Language):**
- `#FFFFFF` / `#F5F5F7` background
- System font stack: `-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif`
- Subtle shadows: `box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08)`
- Rounded corners: `border-radius: 16px`
- Smooth transitions: `transition: all 0.3s ease`
- Blue accent: `#007AFF` (or keep dark theme consistent with TBU brand)

---

### 2. Assembly Editor (editor.html)

**Purpose:** Full visual editor for arranging and editing story content.

#### 2.1 Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  [← Back]                    Story Title                    [● Save] [Done] │
│                                                             ↑ unsaved dot   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────┐   ┌──────────────────────────────────────────┐│
│   │     SIDEBAR             │   │              PREVIEW AREA                ││
│   │                         │   │                                          ││
│   │  [Cover Options]        │   │    ┌─────────────────────┐               ││
│   │   ○ Title/Subtitle 1    │   │    │                     │               ││
│   │   ○ Title/Subtitle 2    │   │    │   COVER TEMPLATE    │               ││
│   │   ...                   │   │    │     (scaled)        │               ││
│   │                         │   │    │                     │               ││
│   │  [Thumbnail Options]    │   │    │   01/08             │               ││
│   │   ○ Literal            │   │    └─────────────────────┘               ││
│   │   ○ Symbolic           │   │                                          ││
│   │   ○ Atmospheric        │   │    ┌─────────────────────┐               ││
│   │                         │   │    │                     │               ││
│   │  [Assembly Stats]       │   │    │  EDITORIAL TEMPLATE │               ││
│   │   Total: 8 slides      │   │    │     (scaled)        │               ││
│   │   Enabled: 7           │   │    │                     │               ││
│   │   Photos: 2            │   │    │   02/08             │               ││
│   │                         │   │    └─────────────────────┘               ││
│   │                         │   │                                          ││
│   │  [Export Preview]       │   │    ┌─────────────────────┐               ││
│   │                         │   │    │                     │               ││
│   └─────────────────────────┘   │    │   PHOTO TEMPLATE    │               ││
│                                  │    │     (scaled)        │               ││
│                                  │    │                     │               ││
│                                  │    │   03/08             │               ││
│                                  │    └─────────────────────┘               ││
│                                  │                                          ││
│                                  │    ... (scrollable)                      ││
│                                  └──────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 2.2 Slide Card Components

Each slide in the preview area is a "Slide Card" containing:

```
┌─────────────────────────────────────────────────────────────────┐
│ [⋮⋮] Drag Handle        [COVER]        [Toggle: ●───○]  [Edit] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                    ┌────────────────────┐                       │
│                    │                    │                       │
│                    │   Template iframe  │                       │
│                    │   (scaled to ~350px│                       │
│                    │    width)          │                       │
│                    │                    │                       │
│                    └────────────────────┘                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Elements:**
- Drag handle (left) — for reordering via SortableJS
- Template type badge — COVER / TEXT / PHOTO
- Toggle switch — default ON, when OFF the slide is dimmed and excluded from export
- Edit button — opens inline edit mode or modal
- Scaled iframe — actual template rendered at scaled size

#### 2.3 Save Behavior (Explicit Save Only)

**All changes are held in-memory until the user clicks the Save button.**

- **No Auto-Save:** Reordering, toggling, editing text, swapping photos — none of these trigger a database save automatically.
- **Save Button:** Prominent button in the header. When clicked, the entire assembly state is POSTed to `/api/stories/{id}/assembly`.
- **Unsaved Changes Indicator:** A small dot (●) appears next to the Save button when there are unsaved changes.
- **Navigation Warning:** If user tries to navigate away (back button, close tab) with unsaved changes, show a browser confirmation dialog.
- **Save Confirmation:** Brief success toast or checkmark animation when save completes.

```
┌─────────────────────────────────────────────────────────────┐
│  [← Back]          Story Title           [● Save]  [Done]   │
│                                           ↑                 │
│                                    Blue dot = unsaved       │
│                                    No dot = all saved       │
└─────────────────────────────────────────────────────────────┘
```

---

#### 2.4 Core Interactions

**A. Drag & Drop Reordering**
- Use [SortableJS](https://sortablejs.github.io/Sortable/) for drag-and-drop
- When order changes:
  1. Update internal state array (in-memory only)
  2. Recalculate page numbers for ALL slides
  3. Send `postMessage` to each iframe to update its page number
  4. Mark assembly as "dirty" (show unsaved changes indicator)
  5. Changes are NOT persisted until user clicks Save button

**B. Dynamic Page Numbers**
- Format: `01/08`, `02/08`, etc.
- Only count ENABLED slides when calculating total
- On toggle or reorder, recalculate and update all iframes

**C. Toggle Slide Visibility**
- Toggle switch for each slide
- When OFF:
  - Slide card gets opacity: 0.4 and grayscale filter
  - Slide is excluded from page count
  - `assembly_data.slides[n].visible = false`
- Default: All slides visible

**D. Cover Customization**
- **Title/Subtitle Switcher:** Radio group in sidebar
  - Fetches all `story_generations` for this story (there may be multiple)
  - Shows each as an option: "Title: [hook_title] / [subtitle]"
  - Selecting one updates the cover iframe via postMessage
  
- **Thumbnail Switcher:** Radio group with image previews
  - Fetches all `story_thumbnails` for the selected story_generation
  - Shows 3 concepts (literal, symbolic, atmospheric)
  - Selecting one updates the cover iframe background

**E. Inline Text Editing**
- Click "Edit" on any TEXT slide → opens edit mode
- Options:
  1. **Inline via postMessage:** Send signal to iframe to make `.text-column` contenteditable
  2. **Modal Editor:** Opens modal with textarea, preview button, apply button
- Changes update local state only (NOT saved to DB until user clicks Save)
- Changes persist to `assembly_data.slides[n].content.text` in memory

**F. Photo Swapping**
- Click "Edit" on any PHOTO slide → opens photo picker modal
- Shows all `story_photos` with `status = 'approved'` for this story
- Each photo shows thumbnail, caption, source
- Selecting one updates:
  - The photo iframe via postMessage
  - `assembly_data.slides[n].content.image_url`
  - `assembly_data.slides[n].content.caption`
  - `assembly_data.slides[n].content.source`

---

## Data Structures

### Assembly JSON Schema (stored in `story_assemblies.assembly_data`)

```json
{
  "version": 1,
  "story_generation_id": "uuid",
  "selected_thumbnail_id": "uuid",
  "slides": [
    {
      "id": "slide-uuid-1",
      "type": "cover",
      "template": "cover3",
      "visible": true,
      "content": {
        "title": "Why Does Déjà Vu Feel Real?",
        "subtitle": "These classified CIA documents may hold...",
        "thumbnail_url": "https://...",
        "domain_tag": "NEUROSCIENCE"
      }
    },
    {
      "id": "slide-uuid-2",
      "type": "text",
      "template": "editorial3",
      "visible": true,
      "content": {
        "text": "Scientists have long suspected...",
        "paragraph_count": 2,
        "domain_tag": "DÉJÀ VU"
      }
    },
    {
      "id": "slide-uuid-3",
      "type": "photo",
      "template": "photos1",
      "visible": true,
      "content": {
        "image_url": "https://...",
        "caption": "Fig 1.1: Early conceptualization...",
        "source": "Source: Archives / Dept 4",
        "domain_tag": "DÉJÀ VU"
      }
    }
    // ... more slides
  ],
  "metadata": {
    "created_at": "2025-12-18T...",
    "updated_at": "2025-12-18T...",
    "last_edited_by": "user"
  }
}
```

### Default Assembly Generation Algorithm

When a user opens a story for the first time (no existing assembly):

```python
def generate_default_assembly(story_generation_id):
    """
    Creates default slide order:
    1. Cover (always first)
    2. Text slides in order
    3. Photos interspersed every 2-3 text slides
    """
    
    # Fetch data
    generation = get_story_generation(story_generation_id)
    slides = get_story_slides(story_generation_id)  # ordered by slide_order
    photos = get_approved_photos(generation.story_research_id)
    thumbnails = get_thumbnails(story_generation_id)
    
    assembly_slides = []
    
    # 1. Cover slide
    selected_thumb = next((t for t in thumbnails if t.is_selected), thumbnails[0])
    assembly_slides.append({
        "id": str(uuid4()),
        "type": "cover",
        "template": "cover3",
        "visible": True,
        "content": {
            "title": generation.hook_title,
            "subtitle": generation.subtitle,
            "thumbnail_url": selected_thumb.image_url,
            "domain_tag": generation.domain_tag
        }
    })
    
    # 2. Interleave text and photos
    photo_positions = distribute_photos(len(slides), len(photos))
    # e.g., [2, 5] means insert photos after slides 2 and 5
    
    photo_index = 0
    for i, slide in enumerate(slides):
        # Add text slide
        assembly_slides.append({
            "id": str(uuid4()),
            "type": "text",
            "template": "editorial3",
            "visible": True,
            "content": {
                "text": slide.text_content,
                "paragraph_count": slide.paragraph_count,
                "domain_tag": generation.domain_tag
            },
            "source_slide_id": str(slide.id)
        })
        
        # Insert photo if at designated position
        if i in photo_positions and photo_index < len(photos):
            photo = photos[photo_index]
            assembly_slides.append({
                "id": str(uuid4()),
                "type": "photo",
                "template": "photos1",
                "visible": True,
                "content": {
                    "image_url": photo.image_url,
                    "caption": photo.caption,
                    "source": photo.source_attribution,
                    "domain_tag": generation.domain_tag
                },
                "source_photo_id": str(photo.id)
            })
            photo_index += 1
    
    return assembly_slides
```

---

## Technical Architecture

### Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Backend | FastAPI | REST API, static file serving |
| Database | PostgreSQL (Supabase) | Data persistence |
| Frontend | HTML + Alpine.js | Reactive UI, minimal overhead |
| Drag & Drop | SortableJS | Reordering slides |
| Template Rendering | iframes + postMessage | Isolated template display |
| Styling | Tailwind CSS (via CDN) | Apple-style aesthetics |

### Why This Stack?

- **FastAPI:** Lightweight, fast, async-ready, perfect for serving static + API
- **Alpine.js:** Minimal JS framework, perfect for this level of interactivity without build tools
- **iframes:** Ensures templates render exactly as they will in final export (no CSS conflicts)
- **Tailwind:** Rapid styling, easy to achieve Apple-like aesthetics
- **postMessage:** Clean communication channel between editor and template iframes

---

## File Structure

```
pre_assembler/
├── main.py                  # FastAPI app entry point
├── config.py                # Environment variables
├── db.py                    # Database connection & queries
├── models.py                # Pydantic models for API
├── routes/
│   ├── __init__.py
│   ├── stories.py           # GET /api/stories, GET /api/stories/{id}
│   ├── assemblies.py        # GET/POST /api/stories/{id}/assembly
│   └── templates.py         # GET /api/templates/{type}/{id}
├── services/
│   ├── __init__.py
│   └── assembly.py          # Default assembly generation logic
├── static/
│   ├── index.html           # Dashboard page
│   ├── editor.html          # Assembly editor page
│   ├── css/
│   │   └── app.css          # Custom styles (if any beyond Tailwind)
│   ├── js/
│   │   ├── dashboard.js     # Dashboard Alpine component
│   │   ├── editor.js        # Editor Alpine component
│   │   └── template-bridge.js  # postMessage helpers
│   └── img/
│       └── ...              # Any UI assets
├── templates/               # Symlinked from template_design/chosen_templates
│   ├── cover3.html
│   ├── editorial3.html
│   ├── photos1.html
│   └── videos1.html
├── wrapper/
│   └── template_wrapper.js  # Injected into templates for postMessage handling
├── schema.sql
├── requirements.txt
├── README.md
└── PLAN.md
```

---

## API Endpoints

### Stories

**`GET /api/stories`**
Returns list of stories ready for assembly.

```json
{
  "stories": [
    {
      "id": "uuid",
      "story_research_id": "uuid",
      "story_generation_id": "uuid",
      "hook_title": "Why Does Déjà Vu Feel Real?",
      "subtitle": "These classified CIA documents...",
      "domain_tag": "NEUROSCIENCE",
      "thumbnail_url": "https://...",
      "slide_count": 8,
      "photo_count": 3,
      "assembly_status": "draft" | "in_progress" | "finalized",
      "created_at": "2025-12-18T...",
      "updated_at": "2025-12-18T..."
    }
  ]
}
```

**`GET /api/stories/{story_generation_id}`**
Returns full story data for assembly editor.

```json
{
  "story": {
    "id": "uuid",
    "hook_title": "...",
    "subtitle": "...",
    "domain_tag": "..."
  },
  "generations": [
    {
      "id": "uuid",
      "hook_title": "...",
      "subtitle": "...",
      "domain_tag": "..."
    }
  ],
  "slides": [
    {
      "id": "uuid",
      "slide_order": 1,
      "text_content": "...",
      "paragraph_count": 2
    }
  ],
  "photos": [
    {
      "id": "uuid",
      "image_url": "...",
      "caption": "...",
      "source_attribution": "...",
      "status": "approved"
    }
  ],
  "thumbnails": [
    {
      "id": "uuid",
      "concept_type": "literal",
      "image_url": "...",
      "is_selected": true
    }
  ]
}
```

### Assemblies

**`GET /api/stories/{story_generation_id}/assembly`**
Returns existing assembly or generates default.

```json
{
  "assembly": {
    "id": "uuid",
    "story_generation_id": "uuid",
    "assembly_data": { ... },
    "status": "draft",
    "created_at": "...",
    "updated_at": "..."
  },
  "is_default": true  // if newly generated
}
```

**`POST /api/stories/{story_generation_id}/assembly`**
Saves assembly configuration.

Request body:
```json
{
  "assembly_data": { ... },
  "status": "draft" | "finalized"
}
```

### Templates

**`GET /api/templates/{template_type}`**
Returns template HTML with wrapper script injected.

Query params:
- `slide_id`: UUID to track which slide this is
- `content`: Base64-encoded JSON of slide content

Returns: HTML with injected JavaScript for postMessage handling.

---

## Template Wrapper System

Each template iframe loads with an injected script that:

1. **Receives messages** from parent (editor) to update content
2. **Sends messages** to parent when user edits content (if contenteditable)
3. **Handles page number updates** dynamically

### wrapper/template_wrapper.js

```javascript
(function() {
  // Listen for messages from parent (editor)
  window.addEventListener('message', function(event) {
    const { type, payload } = event.data;
    
    switch(type) {
      case 'UPDATE_PAGE_NUMBER':
        updatePageNumber(payload.current, payload.total);
        break;
        
      case 'UPDATE_CONTENT':
        updateContent(payload);
        break;
        
      case 'SET_EDITABLE':
        setContentEditable(payload.editable);
        break;
    }
  });
  
  // Update page number display
  function updatePageNumber(current, total) {
    const el = document.querySelector('.page-number, .footer-left');
    if (el) {
      const formatted = `${String(current).padStart(2, '0')} / ${String(total).padStart(2, '0')}`;
      // Handle both formats in templates
      if (el.innerHTML.includes('SWIPE')) {
        el.innerHTML = `${formatted}<br>SWIPE FOR MORE`;
      } else {
        el.textContent = formatted;
      }
    }
  }
  
  // Update template content based on type
  function updateContent(content) {
    // Cover template
    if (content.title) {
      const title = document.querySelector('.main-title');
      if (title) title.innerHTML = content.title.replace(/\n/g, '<br>');
    }
    if (content.subtitle) {
      const subtitle = document.querySelector('.subtitle');
      if (subtitle) subtitle.textContent = content.subtitle;
    }
    if (content.thumbnail_url) {
      const bg = document.querySelector('.bg-image');
      if (bg) bg.src = content.thumbnail_url;
    }
    
    // Editorial template
    if (content.text) {
      const col = document.querySelector('.text-column');
      if (col) {
        // Split into paragraphs
        const paragraphs = content.text.split('\n\n').filter(p => p.trim());
        col.innerHTML = paragraphs.map(p => `<p>${p}</p>`).join('');
      }
    }
    
    // Photo template
    if (content.image_url) {
      const img = document.querySelector('.display-photo, #main-photo');
      if (img) img.src = content.image_url;
    }
    if (content.caption) {
      const cap = document.querySelector('.caption-text, #caption-text');
      if (cap) cap.textContent = content.caption;
    }
    if (content.source) {
      const src = document.querySelector('.source-text, #source-text');
      if (src) src.textContent = content.source;
    }
    
    // Domain tag (meta-data area)
    if (content.domain_tag) {
      const meta = document.querySelector('.meta-data');
      if (meta) meta.innerHTML = content.domain_tag;
    }
  }
  
  // Enable/disable content editing
  function setContentEditable(editable) {
    const editableSelectors = [
      '.main-title',
      '.subtitle',
      '.text-column',
      '.caption-text'
    ];
    
    editableSelectors.forEach(sel => {
      const el = document.querySelector(sel);
      if (el) {
        el.contentEditable = editable;
        if (editable) {
          el.style.outline = '2px dashed rgba(0, 122, 255, 0.5)';
          el.addEventListener('blur', notifyContentChange);
        } else {
          el.style.outline = 'none';
          el.removeEventListener('blur', notifyContentChange);
        }
      }
    });
  }
  
  function notifyContentChange(event) {
    const content = {
      title: document.querySelector('.main-title')?.textContent,
      subtitle: document.querySelector('.subtitle')?.textContent,
      text: document.querySelector('.text-column')?.textContent,
      caption: document.querySelector('.caption-text')?.textContent
    };
    
    window.parent.postMessage({
      type: 'CONTENT_CHANGED',
      slideId: window.__slideId,
      content: content
    }, '*');
  }
  
  // Signal ready
  window.parent.postMessage({ type: 'TEMPLATE_READY', slideId: window.__slideId }, '*');
})();
```

---

## Database Schema

### Updated schema.sql

```sql
-- Story assemblies table
CREATE TABLE IF NOT EXISTS public.story_assemblies (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    story_generation_id uuid NOT NULL,
    assembly_data jsonb NOT NULL,
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'in_progress', 'finalized')),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT story_assemblies_pkey PRIMARY KEY (id),
    CONSTRAINT story_assemblies_story_generation_id_fkey FOREIGN KEY (story_generation_id) REFERENCES public.story_generations(id)
);

-- Allow multiple assemblies per story (different versions/drafts)
-- But typically we'll work with the latest one
CREATE INDEX idx_story_assemblies_generation ON public.story_assemblies(story_generation_id);
CREATE INDEX idx_story_assemblies_status ON public.story_assemblies(status);

-- Auto-update updated_at
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
```

---

## Implementation Phases

### Phase 1: Foundation (Day 1-2)

**Goal:** Basic infrastructure and data flow.

- [ ] Set up FastAPI app with static file serving
- [ ] Create `db.py` with connection pooling
- [ ] Implement `GET /api/stories` endpoint
- [ ] Implement `GET /api/stories/{id}` endpoint
- [ ] Create basic `index.html` dashboard with story cards
- [ ] Symlink templates folder

**Deliverable:** Can view list of ready stories in browser.

### Phase 2: Assembly Editor Structure (Day 3-4)

**Goal:** Basic editor layout with iframe rendering.

- [ ] Create `editor.html` with sidebar + preview layout
- [ ] Implement assembly default generation logic
- [ ] Implement `GET /api/stories/{id}/assembly` endpoint
- [ ] Render slides as iframes in preview area
- [ ] Create template serving endpoint with wrapper injection
- [ ] Basic postMessage communication for content injection

**Deliverable:** Can see story slides rendered in iframes.

### Phase 3: Interactivity (Day 5-6)

**Goal:** Full editing capabilities.

- [ ] Implement SortableJS drag-and-drop
- [ ] Dynamic page number recalculation
- [ ] Toggle slide visibility (on/off switches)
- [ ] Cover title/subtitle switcher (sidebar radio group)
- [ ] Cover thumbnail switcher (sidebar with image previews)
- [ ] Implement `POST /api/stories/{id}/assembly` (save)

**Deliverable:** Can reorder slides, toggle visibility, change cover options.

### Phase 4: Content Editing (Day 7-8)

**Goal:** Text and photo editing.

- [ ] Edit button on each slide card
- [ ] Text editing modal/inline mode
- [ ] Photo swapping modal with approved photo gallery
- [ ] Caption/source editing for photos
- [ ] Unsaved changes indicator (visual badge/dot on Save button)
- [ ] "Unsaved changes" warning when navigating away (beforeunload)

**Deliverable:** Can edit all text and swap photos.

### Phase 5: Polish & UX (Day 9-10)

**Goal:** Production-ready experience.

- [ ] Apple-style visual polish (Tailwind refinements)
- [ ] Loading states and transitions
- [ ] Error handling and user feedback (toasts)
- [ ] Keyboard shortcuts (Cmd+S to save, Esc to cancel)
- [ ] Mobile responsiveness (basic)
- [ ] Export preview mode (shows only enabled slides)
- [ ] Testing across browsers

**Deliverable:** Polished, production-ready tool.

---

## Apple Design System Reference

### Colors (Light Theme)

```css
:root {
  --bg-primary: #FFFFFF;
  --bg-secondary: #F5F5F7;
  --bg-tertiary: #E8E8ED;
  
  --text-primary: #1D1D1F;
  --text-secondary: #6E6E73;
  --text-tertiary: #86868B;
  
  --accent: #007AFF;
  --accent-hover: #0056B3;
  
  --success: #34C759;
  --warning: #FF9500;
  --danger: #FF3B30;
  
  --border: rgba(0, 0, 0, 0.1);
  --shadow: rgba(0, 0, 0, 0.08);
}
```

### Typography

```css
body {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", 
               "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 17px;
  line-height: 1.47059;
  letter-spacing: -0.022em;
  color: var(--text-primary);
}

h1 { font-size: 48px; font-weight: 700; letter-spacing: -0.003em; }
h2 { font-size: 32px; font-weight: 700; letter-spacing: 0.007em; }
h3 { font-size: 24px; font-weight: 600; letter-spacing: 0.009em; }
```

### Components

```css
/* Card */
.card {
  background: var(--bg-primary);
  border-radius: 16px;
  box-shadow: 0 4px 20px var(--shadow);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}
.card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 32px var(--shadow);
}

/* Button */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 12px 24px;
  border-radius: 12px;
  font-weight: 500;
  transition: all 0.2s ease;
}
.btn-primary {
  background: var(--accent);
  color: white;
}
.btn-primary:hover {
  background: var(--accent-hover);
}

/* Toggle Switch */
.toggle {
  width: 51px;
  height: 31px;
  border-radius: 15.5px;
  background: var(--bg-tertiary);
  position: relative;
  cursor: pointer;
  transition: background 0.3s ease;
}
.toggle.active {
  background: var(--success);
}
.toggle::after {
  content: '';
  position: absolute;
  width: 27px;
  height: 27px;
  border-radius: 50%;
  background: white;
  top: 2px;
  left: 2px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
  transition: transform 0.3s ease;
}
.toggle.active::after {
  transform: translateX(20px);
}
```

---

## Dependencies

### requirements.txt

```
fastapi==0.109.0
uvicorn[standard]==0.27.0
psycopg2-binary==2.9.9
python-dotenv==1.0.0
pydantic==2.5.3
jinja2==3.1.3
```

### Frontend (via CDN in HTML)

```html
<!-- Tailwind CSS -->
<script src="https://cdn.tailwindcss.com"></script>

<!-- Alpine.js -->
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>

<!-- SortableJS -->
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js"></script>
```

---

## Key Considerations

### Performance

- **Iframe Scaling:** Iframes are set to actual template size (1080x1350) then CSS scaled down for preview. This ensures pixel-perfect rendering.
- **Lazy Loading:** Only render visible iframes; use IntersectionObserver for slides outside viewport.
- **No Auto-Save:** All changes are held in-memory until explicit Save button click. This avoids constant API calls and gives user full control.

### Data Integrity

- **Explicit Save Only:** User must click Save button to persist changes to database.
- **Unsaved Changes Warning:** Visual indicator when there are unsaved changes; prompt user if navigating away.
- **Conflict Detection:** Compare `updated_at` timestamps before saving (in case another session modified).
- **Undo Support:** Keep last 5 states in memory for Cmd+Z.

### Accessibility

- **Keyboard Navigation:** All interactive elements focusable.
- **ARIA Labels:** Drag handles, toggles, and buttons properly labeled.
- **Focus Trapping:** Modals trap focus appropriately.

---

## Future Enhancements (v2+)

1. **Export Integration:** Direct "Export to PNG" button (calls separate html-to-png service)
2. **Version History:** View and restore previous assembly versions
3. **Collaborative Editing:** Real-time sync if multiple users
4. **Template Variations:** Allow choosing between multiple template styles
5. **Preview Mode:** Full-screen Instagram-style swipe preview
6. **Scheduling:** Set publish date/time after assembly
7. **Analytics Integration:** Track which cover/thumbnail combinations perform best

---

## Getting Started

```bash
# 1. Navigate to pre_assembler
cd code/pre_assembler

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create symlink to templates
ln -s ../template_design/chosen_templates templates

# 5. Run the server
uvicorn main:app --reload --port 8000

# 6. Open in browser
open http://localhost:8000
```

---

## Summary

This plan provides a complete blueprint for building the Pre-Assembler web tool. It balances sophistication with simplicity by:

- Using iframes for perfect template fidelity
- Leveraging Alpine.js for reactive UI without build complexity
- Implementing postMessage for clean parent-child communication
- Following Apple's design language for a polished, professional feel
- Breaking implementation into clear, achievable phases

The result will be a tool that makes reviewing and finalizing Instagram content a smooth, visual, and enjoyable process.
