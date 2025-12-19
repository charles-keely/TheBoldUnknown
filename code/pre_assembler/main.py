"""
Pre-Assembler FastAPI Application

A web-based tool for assembling and reviewing Instagram carousel stories.
"""

import os
import uuid
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import config
from db import (
    get_stories_ready_for_assembly,
    get_story_full_data,
    get_assembly,
    save_assembly,
    check_db_connection
)
from models import (
    StoriesResponse,
    StorySummary,
    StoryFullData,
    StoryInfo,
    StoryGeneration,
    StorySlide,
    StoryPhoto,
    StoryThumbnail,
    AssemblyResponse,
    Assembly,
    AssemblyData,
    AssemblySlide,
    SlideContent,
    AssemblyMetadata,
    SaveAssemblyRequest,
    SaveAssemblyResponse,
    AssemblyStatus,
    SlideType,
    TemplateType
)

# =============================================================================
# App Setup
# =============================================================================

app = FastAPI(
    title="TheBoldUnknown Pre-Assembler",
    description="Web tool for assembling Instagram carousel stories",
    version="1.0.0"
)

# CORS (allow all for local development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Static File Mounts
# =============================================================================

# Mount static files (CSS, JS, etc.)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

# Mount template design assets (images for templates)
template_img_dir = os.path.join(config.TEMPLATE_DESIGN_DIR, 'img')
if os.path.exists(template_img_dir):
    app.mount("/template-assets/img", StaticFiles(directory=template_img_dir), name="template-img")

# Mount chosen templates
chosen_templates_dir = os.path.join(config.TEMPLATE_DESIGN_DIR, 'chosen_templates')
if os.path.exists(chosen_templates_dir):
    app.mount("/templates", StaticFiles(directory=chosen_templates_dir), name="templates")


# =============================================================================
# Page Routes
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard page."""
    index_path = os.path.join(config.STATIC_DIR, 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Pre-Assembler Dashboard</h1><p>index.html not found</p>")


@app.get("/editor/{story_generation_id}", response_class=HTMLResponse)
async def editor(story_generation_id: str):
    """Serve the assembly editor page."""
    editor_path = os.path.join(config.STATIC_DIR, 'editor.html')
    if os.path.exists(editor_path):
        return FileResponse(editor_path)
    return HTMLResponse("<h1>Assembly Editor</h1><p>editor.html not found</p>")


# =============================================================================
# API Routes - Stories
# =============================================================================

@app.get("/api/stories", response_model=StoriesResponse)
async def list_stories():
    """
    Get all stories ready for assembly.
    
    Stories must have:
    - Completed research
    - At least 1 text slide
    - At least 1 approved photo
    - At least 1 generated thumbnail
    - NOT finalized in assembly
    """
    rows = get_stories_ready_for_assembly()
    
    stories = []
    for row in rows:
        # Construct thumbnail URL from thumbnail_id
        thumbnail_url = None
        if row.get('thumbnail_id'):
            thumbnail_url = f"/api/thumbnails/{row['thumbnail_id']}/image"
        
        stories.append(StorySummary(
            story_generation_id=str(row['story_generation_id']),
            story_research_id=str(row['story_research_id']),
            hook_title=row['hook_title'],
            subtitle=row['subtitle'],
            domain_tag=row['domain_tag'],
            slide_count=row['slide_count'],
            photo_count=row['photo_count'],
            thumbnail_url=thumbnail_url,
            thumbnail_count=row['thumbnail_count'],
            assembly_status=AssemblyStatus(row['assembly_status']) if row['assembly_status'] in [s.value for s in AssemblyStatus] else AssemblyStatus.NEW,
            created_at=row['created_at'],
            updated_at=row['updated_at']
        ))
    
    return StoriesResponse(stories=stories, count=len(stories))


@app.get("/api/stories/{story_generation_id}")
async def get_story(story_generation_id: str):
    """
    Get full story data for the assembly editor.
    
    Returns all generations (title variations), slides, photos, and thumbnails.
    """
    data = get_story_full_data(story_generation_id)
    
    if not data:
        raise HTTPException(status_code=404, detail="Story not found")
    
    return {
        "story": data['story'],
        "generations": data['generations'],
        "slides": data['slides'],
        "photos": data['photos'],
        "thumbnails": data['thumbnails']
    }


# =============================================================================
# API Routes - Assemblies
# =============================================================================

@app.get("/api/stories/{story_generation_id}/assembly")
async def get_or_create_assembly(story_generation_id: str):
    """
    Get existing assembly or generate a default one.
    
    Default assembly order:
    1. Cover (first)
    2. Text slides in order
    3. Photos interspersed after every 2-3 text slides
    """
    # Check if assembly exists
    existing = get_assembly(story_generation_id)
    
    if existing:
        return {
            "assembly": {
                "id": str(existing['id']),
                "story_generation_id": str(existing['story_generation_id']),
                "assembly_data": existing['assembly_data'],
                "status": existing['status'],
                "created_at": existing['created_at'],
                "updated_at": existing['updated_at']
            },
            "is_default": False
        }
    
    # Generate default assembly
    story_data = get_story_full_data(story_generation_id)
    if not story_data:
        raise HTTPException(status_code=404, detail="Story not found")
    
    default_assembly = generate_default_assembly(story_data)
    
    return {
        "assembly": {
            "id": None,
            "story_generation_id": story_generation_id,
            "assembly_data": default_assembly,
            "status": "new",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        },
        "is_default": True
    }


@app.post("/api/stories/{story_generation_id}/assembly")
async def save_story_assembly(story_generation_id: str, request: SaveAssemblyRequest):
    """
    Save assembly configuration.
    
    This is called when the user clicks the Save button.
    """
    try:
        # Convert to dict for storage
        assembly_dict = request.assembly_data.model_dump()
        
        # Update metadata
        now = datetime.now()
        if 'metadata' not in assembly_dict or not assembly_dict['metadata']:
            assembly_dict['metadata'] = {
                'created_at': now.isoformat(),
                'updated_at': now.isoformat()
            }
        else:
            assembly_dict['metadata']['updated_at'] = now.isoformat()
        
        assembly_id = save_assembly(
            story_generation_id,
            assembly_dict,
            request.status.value
        )
        
        return SaveAssemblyResponse(
            id=str(assembly_id),
            status=request.status,
            updated_at=now
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Thumbnail Image Endpoint
# =============================================================================

@app.get("/api/thumbnails/{thumbnail_id}/image")
async def get_thumbnail_image(thumbnail_id: str):
    """
    Serve thumbnail image from database.
    
    Thumbnails are stored as base64 in generation_metadata.image_base64.
    This endpoint decodes and serves the image.
    """
    from fastapi.responses import Response
    from db import get_db_connection
    import base64
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT generation_metadata
                FROM story_thumbnails
                WHERE id = %s
            """, (thumbnail_id,))
            row = cur.fetchone()
            
            if not row or not row['generation_metadata']:
                raise HTTPException(status_code=404, detail="Thumbnail not found")
            
            metadata = row['generation_metadata']
            if 'image_base64' not in metadata:
                raise HTTPException(status_code=404, detail="Thumbnail image not found")
            
            # Decode base64 image
            image_data = base64.b64decode(metadata['image_base64'])
            mime_type = metadata.get('mime_type', 'image/png')
            
            return Response(
                content=image_data,
                media_type=mime_type,
                headers={"Cache-Control": "public, max-age=86400"}  # Cache for 24 hours
            )
    finally:
        conn.close()


# =============================================================================
# Health Check
# =============================================================================

@app.get("/api/health")
async def health_check():
    """Check API and database health."""
    db_ok = check_db_connection()
    return {
        "status": "healthy" if db_ok else "unhealthy",
        "database": "connected" if db_ok else "disconnected"
    }


# =============================================================================
# Helper Functions
# =============================================================================

def generate_default_assembly(story_data: dict) -> dict:
    """
    Generate a default assembly from story data.
    
    Order:
    1. Cover slide (always first)
    2. Text slides in original order
    3. Photo slides interspersed every 2-3 text slides
    """
    story = story_data['story']
    slides = story_data['slides']
    photos = story_data['photos']
    thumbnails = story_data['thumbnails']
    
    assembly_slides = []
    
    # Get selected thumbnail (or first one)
    selected_thumb = None
    for t in thumbnails:
        if t.get('is_selected'):
            selected_thumb = t
            break
    if not selected_thumb and thumbnails:
        selected_thumb = thumbnails[0]
    
    # 1. Cover slide
    assembly_slides.append({
        "id": str(uuid.uuid4()),
        "type": SlideType.COVER.value,
        "template": TemplateType.COVER3.value,
        "visible": True,
        "content": {
            "title": story['hook_title'],
            "subtitle": story['subtitle'],
            "thumbnail_url": selected_thumb['image_url'] if selected_thumb else None,
            "domain_tag": story['domain_tag']
        }
    })
    
    # 2. Distribute photos among text slides
    # Insert photos after slide indices: [2, 5] for 7 slides, etc.
    photo_positions = distribute_photos(len(slides), len(photos))
    
    photo_index = 0
    for i, slide in enumerate(slides):
        # Add text slide
        assembly_slides.append({
            "id": str(uuid.uuid4()),
            "type": SlideType.TEXT.value,
            "template": TemplateType.EDITORIAL3.value,
            "visible": True,
            "content": {
                "text": slide['text_content'],
                "paragraph_count": slide.get('paragraph_count'),
                "domain_tag": story['domain_tag']
            },
            "source_slide_id": str(slide['id'])
        })
        
        # Insert photo if at designated position
        if i in photo_positions and photo_index < len(photos):
            photo = photos[photo_index]
            assembly_slides.append({
                "id": str(uuid.uuid4()),
                "type": SlideType.PHOTO.value,
                "template": TemplateType.PHOTOS1.value,
                "visible": True,
                "content": {
                    "image_url": photo['image_url'],
                    "caption": photo.get('caption', ''),
                    "source": photo.get('source_attribution', ''),
                    "domain_tag": story['domain_tag']
                },
                "source_photo_id": str(photo['id'])
            })
            photo_index += 1
    
    return {
        "version": 1,
        "story_generation_id": str(story['story_generation_id']),
        "selected_thumbnail_id": str(selected_thumb['id']) if selected_thumb else None,
        "slides": assembly_slides,
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    }


def distribute_photos(text_count: int, photo_count: int) -> list:
    """
    Calculate positions to insert photos among text slides.
    
    Strategy: Spread photos evenly throughout the text slides.
    Returns list of text slide indices after which to insert photos.
    """
    if photo_count == 0 or text_count == 0:
        return []
    
    # Simple distribution: insert after every N text slides
    # where N = text_count / (photo_count + 1)
    positions = []
    interval = text_count / (photo_count + 1)
    
    for i in range(photo_count):
        pos = int((i + 1) * interval) - 1  # 0-indexed position
        pos = max(0, min(pos, text_count - 1))  # Clamp to valid range
        positions.append(pos)
    
    return positions


# =============================================================================
# Run
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG
    )
