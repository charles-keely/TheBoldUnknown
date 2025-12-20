# TheBoldUnknown Pre-Assembler

A web-based tool for visually assembling and reviewing Instagram carousel stories before final rendering to PNG.

## Overview

The Pre-Assembler is the final editing stage before Instagram publication. It allows you to:

- **Browse** all stories with complete content (text, photos, thumbnails)
- **Preview** stories rendered in their actual HTML templates
- **Reorder** slides via drag-and-drop
- **Toggle** individual slides on/off for final export
- **Edit** text and swap photos inline
- **Switch** between cover title/subtitle variations and thumbnail options
- **Save** the final assembly configuration

## Features

### Story Dashboard
- Grid view of all stories ready for assembly
- Apple-style design with clean cards and smooth interactions
- Status indicators (Draft, In Progress, Finalized)

### Assembly Editor
- Instagram feed-style vertical scroll preview
- Real-time template rendering in iframes
- Drag-and-drop slide reordering with SortableJS
- Dynamic page number updates (01/08, 02/08, etc.)
- Toggle visibility for each slide
- Cover customization:
  - Switch between title/subtitle variations
  - Choose from 3 thumbnail concepts (Literal, Symbolic, Atmospheric)
- Inline text editing
- Photo swapping from approved images

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI |
| Database | PostgreSQL (Supabase) |
| Frontend | HTML + Alpine.js + Tailwind CSS |
| Drag & Drop | SortableJS |
| Template Rendering | iframes + postMessage |

## Setup

### 1. Install Dependencies

```bash
cd code/pre_assembler
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Create Template Symlink

```bash
ln -s ../template_design/chosen_templates templates
```

### 3. Environment Variables

Ensure your `code/.env` file has the database credentials:

```ini
POSTGRES_HOST=your-host.supabase.co
POSTGRES_PORT=6543
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password
```

### 4. Run Database Migration

```sql
-- Run schema.sql against your database
\i schema.sql
```

### 5. Start the Server

```bash
uvicorn main:app --reload --port 8000
```

### 6. Open in Browser

```
http://localhost:8000
```

## Usage

1. **Dashboard**: See all stories that have completed the content pipeline
2. **Click a story** to open the Assembly Editor
3. **Arrange slides**: Drag to reorder, toggle to include/exclude
4. **Customize cover**: Select title/subtitle and thumbnail options from sidebar
5. **Edit content**: Click edit on any slide to modify text or swap photos
6. **Save**: Assembly is saved to database for later export

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stories` | List all stories ready for assembly |
| GET | `/api/stories/{id}` | Get full story data |
| GET | `/api/stories/{id}/assembly` | Get or generate assembly |
| POST | `/api/stories/{id}/assembly` | Save assembly |
| GET | `/api/templates/{type}` | Serve template with wrapper |

## File Structure

```
pre_assembler/
├── main.py              # FastAPI entry point (routes + business logic)
├── config.py            # Environment config
├── db.py                # Database queries
├── models.py            # Pydantic models
├── static/              # Frontend assets
│   ├── index.html       # Dashboard
│   ├── editor.html      # Assembly editor
│   ├── css/             # Stylesheets
│   └── js/
│       └── template-wrapper.js  # iframe postMessage handler
├── templates/           # Symlink to chosen_templates
├── schema.sql           # Database schema
├── requirements.txt     # Python dependencies
├── README.md            # This file
└── PLAN.md              # Detailed implementation plan
```

## Documentation

See [PLAN.md](PLAN.md) for the comprehensive implementation plan including:
- Full feature specifications
- Data structures and API schemas
- Technical architecture decisions
- Implementation phases
- Apple design system reference

## License

Internal project — TheBoldUnknown
