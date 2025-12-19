# Pre-Assembler Plan

## Goal
Create a web-based "Pre-Assembler" tool to visualize, edit, and organize Instagram story slides before final rendering.

## Core Features
1.  **Dashboard**: List all stories that are "ready for assembly" (have text, photos, and thumbnails).
2.  **Assembly Editor**:
    -   Instagram feed style vertical scroll.
    -   **Drag & Drop**: Reorder slides.
    -   **Toggle Visibility**: Include/exclude slides from final render.
    -   **Dynamic Updates**: Page numbers update automatically (e.g., 01/08).
    -   **Content Editing**:
        -   Edit text directly in the template preview.
        -   Swap photos/thumbnails.
        -   Switch Title/Subtitle variations.
    -   **Save State**: Persist the assembly configuration (order, edits, visibility) to the database.

## Architecture
-   **Backend**: Python (FastAPI).
    -   Serves static frontend assets.
    -   API to fetch story data from PostgreSQL.
    -   API to save/load assembly state.
    -   Serves HTML templates with injected scripts for interactivity.
-   **Frontend**: HTML/JS (Vue.js via CDN or vanilla JS).
    -   Uses `iframe` for each slide to ensure perfect visual fidelity with the templates.
    -   `postMessage` communication between Editor (parent) and Slide (iframe) for updates.
-   **Database**:
    -   New table `story_assemblies` to store the JSON configuration of an assembled story.

## Data Flow
1.  **Load**: Backend fetches `story_generations`, `story_slides`, `story_photos`, `story_thumbnails`.
2.  **Default Assembly**: If no saved assembly exists, backend generates a default order (Cover -> Text -> Photos interleaved).
3.  **Render**: Frontend renders list of iframes.
4.  **Edit**: User interacts with UI (drag, edit text). Frontend updates internal state.
5.  **Preview**: Frontend sends `postMessage` to iframes to update content (e.g., page numbers).
6.  **Save**: JSON state sent to backend and saved to `story_assemblies`.

## Step-by-Step Implementation

### Phase 1: Database & Backend Setup
1.  Create `requirements.txt` (fastapi, uvicorn, psycopg2-binary, python-dotenv).
2.  Create `schema.sql` with `story_assemblies` table.
3.  Set up `db.py` for database connection.
4.  Create `main.py` with FastAPI app and static mounts.

### Phase 2: Template Adaptation
1.  Copy/Link templates from `template_design/chosen_templates` to `pre_assembler/templates`.
2.  Create `template_wrapper.js`: A script to be injected into templates that:
    -   Listens for `postMessage` (update content).
    -   Handles `contenteditable` changes and emits events back to parent.
3.  Create endpoints to serve templates with this wrapper injected.

### Phase 3: API Development
1.  `GET /api/stories`: List stories with status 'completed' (or custom logic).
2.  `GET /api/stories/{id}/assembly`: Fetch existing assembly or generate default structure.
    -   Default structure: [Cover, Text1, Text2, Photo1, Text3...]
3.  `POST /api/stories/{id}/assembly`: Save JSON payload.

### Phase 4: Frontend Development
1.  **Dashboard (`index.html`)**: Grid of stories.
2.  **Editor (`editor.html`)**:
    -   Sidebar: Controls (Save, Back).
    -   Main: List of `iframe` containers.
    -   Use `SortableJS` for drag-and-drop.
    -   Vue.js (or Alpine.js) for state management.
3.  **Interactivity**:
    -   Implement "Swap Thumbnail" modal.
    -   Implement "Toggle Slide" logic.
    -   Implement "Page Number" calculation.

## Folder Structure
```
pre_assembler/
  ├── main.py
  ├── db.py
  ├── models.py
  ├── schema.sql
  ├── requirements.txt
  ├── static/
  │   ├── css/
  │   ├── js/
  │   ├── index.html
  │   └── editor.html
  └── templates/ (symlinked or copied)
```

## Schema: `story_assemblies`
```sql
CREATE TABLE public.story_assemblies (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    story_generation_id uuid NOT NULL UNIQUE,
    assembly_data jsonb NOT NULL, -- { slides: [ { type, template, content, visible, ... } ] }
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT story_assemblies_pkey PRIMARY KEY (id),
    CONSTRAINT story_assemblies_story_generation_id_fkey FOREIGN KEY (story_generation_id) REFERENCES public.story_generations(id)
);
```
