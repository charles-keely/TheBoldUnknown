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

"""
NOTE ON IMPORTS:
This module is sometimes run as:
- `uvicorn main:app` from within `code/pre_assembler/`
and sometimes as:
- `uvicorn pre_assembler.main:app` from within `code/`

So we support both package-relative and local-module imports.
"""

try:
    # Package-style imports
    from .config import config
    from .db import (
        get_stories_ready_for_assembly,
        get_story_full_data,
        get_story_caption_and_hashtags,
        get_assembly,
        save_assembly,
        update_story_generation,
        check_db_connection,
        get_db_fingerprint,
    )
    from .models import (
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
        TemplateType,
        UpdateStoryGenerationRequest,
    )
except ImportError:
    # Local-folder imports
    from config import config
    from db import (
        get_stories_ready_for_assembly,
        get_story_full_data,
        get_story_caption_and_hashtags,
        get_assembly,
        save_assembly,
        update_story_generation,
        check_db_connection,
        get_db_fingerprint,
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
        TemplateType,
        UpdateStoryGenerationRequest,
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
        return FileResponse(index_path, headers={"Cache-Control": "no-store"})
    return HTMLResponse("<h1>Pre-Assembler Dashboard</h1><p>index.html not found</p>")


@app.get("/editor/{story_generation_id}", response_class=HTMLResponse)
async def editor(story_generation_id: str):
    """Serve the assembly editor page."""
    editor_path = os.path.join(config.STATIC_DIR, 'editor.html')
    if os.path.exists(editor_path):
        return FileResponse(editor_path, headers={"Cache-Control": "no-store"})
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
            is_enabled=bool(row.get('is_enabled', True)),
            instagram_caption=row.get('instagram_caption'),
            hashtags=row.get('hashtags'),
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


@app.patch("/api/story-generations/{story_generation_id}")
async def patch_story_generation(story_generation_id: str, request: UpdateStoryGenerationRequest):
    """
    Update a title/subtitle option (a story_generations row).
    Used by the editor to persist edits per option.
    """
    try:
        updated = update_story_generation(
            story_generation_id,
            hook_title=request.hook_title,
            subtitle=request.subtitle,
            domain_tag=request.domain_tag,
            is_enabled=request.is_enabled,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Story generation not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# API Routes - Assemblies
# =============================================================================

def _iso_now() -> str:
    return datetime.now().isoformat()


def hydrate_assembly_from_story(
    assembly_data: dict,
    story_data: dict,
    *,
    force: bool = False,
) -> tuple[dict, bool]:
    """
    Re-hydrate an existing assembly's per-slide *content* from DB story tables,
    while preserving slide ordering / visibility / template selection.

    Why:
    - Early assemblies may have been saved with test placeholder content.
    - The "source_*_id" fields point to the canonical DB rows; we can rebuild
      content from those sources.

    Behavior:
    - Hydrates when `force=True` or when metadata.hydrated_from_story != True
    - Overwrites slide.content fields for slides that have source ids.
    - Leaves slides without source ids untouched.
    """
    if not assembly_data or not story_data:
        return assembly_data, False

    metadata = assembly_data.get("metadata") or {}
    already_hydrated = bool(metadata.get("hydrated_from_story"))
    if already_hydrated and not force:
        return assembly_data, False

    story = story_data.get("story") or {}
    generations = story_data.get("generations") or []

    gm = (story.get("generation_metadata") or {}) if isinstance(story.get("generation_metadata"), dict) else {}
    default_selected_option_id = gm.get("selected_id")

    # Respect a selected title/subtitle option if present in the assembly JSON.
    # NOTE: This is an "option id" from generation_metadata.options[*].id (typically 1..6),
    # not a story_generations UUID.
    selected_gen_id = (
        assembly_data.get("selected_generation_id")
        or (str(default_selected_option_id) if default_selected_option_id is not None else None)
        or (str(generations[0].get("id")) if generations else None)
    )
    selected_gen = next((g for g in generations if str(g.get("id")) == str(selected_gen_id)), None)

    story_domain = (selected_gen or {}).get("domain_tag") or story.get("domain_tag")
    story_primary_sources = story.get("primary_sources") or []
    story_primary_source_urls = story.get("primary_source_urls") or []

    slides_by_id = {str(s["id"]): s for s in (story_data.get("slides") or []) if s.get("id")}
    photos_by_id = {str(p["id"]): p for p in (story_data.get("photos") or []) if p.get("id")}
    thumbs_by_id = {str(t["id"]): t for t in (story_data.get("thumbnails") or []) if t.get("id")}

    # Decide selected thumbnail
    selected_thumb_id = (
        assembly_data.get("selected_thumbnail_id")
        or next((str(t["id"]) for t in (story_data.get("thumbnails") or []) if t.get("is_selected")), None)
        or (str(story_data["thumbnails"][0]["id"]) if story_data.get("thumbnails") else None)
    )
    selected_thumb_url = thumbs_by_id.get(selected_thumb_id, {}).get("image_url") if selected_thumb_id else None

    # Hydrate slides
    changed = False
    new_data = dict(assembly_data)
    if str(assembly_data.get("selected_generation_id") or "") != str(selected_gen_id or ""):
        changed = True
    new_data["selected_generation_id"] = selected_gen_id
    new_data["selected_thumbnail_id"] = selected_thumb_id

    # Per-option overrides for title/subtitle/domain_tag (kept in the assembly JSON).
    title_overrides = new_data.get("title_overrides") or {}
    if not isinstance(title_overrides, dict):
        title_overrides = {}
    selected_override = title_overrides.get(str(selected_gen_id)) or {}
    if not isinstance(selected_override, dict):
        selected_override = {}

    new_slides = []
    for slide in (assembly_data.get("slides") or []):
        if not isinstance(slide, dict):
            new_slides.append(slide)
            continue

        s = dict(slide)
        content = dict(s.get("content") or {})

        # Ensure domain tag is present (used in header meta-data)
        if story_domain and content.get("domain_tag") != story_domain:
            content["domain_tag"] = story_domain
            changed = True

        if s.get("type") == SlideType.COVER.value:
            # Cover should reflect the story generation by default
            desired_title = selected_override.get("title") or (selected_gen or {}).get("hook_title") or story.get("hook_title")
            desired_subtitle = (
                selected_override.get("subtitle")
                if "subtitle" in selected_override
                else ((selected_gen or {}).get("subtitle") or story.get("subtitle"))
            )
            desired_domain = selected_override.get("domain_tag") or (selected_gen or {}).get("domain_tag") or story_domain

            if desired_title and content.get("title") != desired_title:
                content["title"] = desired_title
                changed = True
            if desired_subtitle is not None and content.get("subtitle") != desired_subtitle:
                content["subtitle"] = desired_subtitle
                changed = True
            if desired_domain and content.get("domain_tag") != desired_domain:
                content["domain_tag"] = desired_domain
                changed = True
            if selected_thumb_url and content.get("thumbnail_url") != selected_thumb_url:
                content["thumbnail_url"] = selected_thumb_url
                changed = True

        elif s.get("type") == SlideType.TEXT.value:
            src_id = s.get("source_slide_id")
            if src_id and str(src_id) in slides_by_id:
                desired_text = slides_by_id[str(src_id)].get("text_content")
                if desired_text is not None and content.get("text") != desired_text:
                    content["text"] = desired_text
                    changed = True
                desired_paras = slides_by_id[str(src_id)].get("paragraph_count")
                if desired_paras is not None and content.get("paragraph_count") != desired_paras:
                    content["paragraph_count"] = desired_paras
                    changed = True

        elif s.get("type") == SlideType.PHOTO.value:
            src_id = s.get("source_photo_id")
            if src_id and str(src_id) in photos_by_id:
                p = photos_by_id[str(src_id)]
                desired_url = p.get("image_url")
                if desired_url and content.get("image_url") != desired_url:
                    content["image_url"] = desired_url
                    changed = True
                desired_caption = p.get("caption") or ""
                if content.get("caption") != desired_caption:
                    content["caption"] = desired_caption
                    changed = True
                desired_source = p.get("source_attribution") or ""
                if content.get("source") != desired_source:
                    content["source"] = desired_source
                    changed = True

        # Closing slide: keep primary sources in sync with story_research.
        # (We key off template so we don't need a new slide type.)
        if s.get("template") == TemplateType.CLOSING1.value:
            if content.get("primary_sources") != story_primary_sources:
                content["primary_sources"] = story_primary_sources
                changed = True
            if content.get("primary_source_urls") != story_primary_source_urls:
                content["primary_source_urls"] = story_primary_source_urls
                changed = True

        s["content"] = content
        new_slides.append(s)

    new_data["slides"] = new_slides

    # Ensure every assembly ends with the closing slide.
    # Older saved assemblies won't have it, so we append it here.
    has_closing = any(
        isinstance(s, dict) and s.get("template") == TemplateType.CLOSING1.value
        for s in new_slides
    )
    if not has_closing:
        new_slides.append(
            {
                "id": str(uuid.uuid4()),
                "type": SlideType.TEXT.value,
                "template": TemplateType.CLOSING1.value,
                "visible": True,
                "content": {
                    "primary_sources": story_primary_sources,
                    "primary_source_urls": story_primary_source_urls,
                    "domain_tag": story_domain,
                },
            }
        )
        new_data["slides"] = new_slides
        changed = True

    # Mark hydration so we don't keep overwriting manual edits on future loads.
    new_metadata = dict(metadata)
    new_metadata["hydrated_from_story"] = True
    new_metadata["hydrated_at"] = _iso_now()
    # Keep created_at/updated_at fields if present; otherwise populate.
    new_metadata.setdefault("created_at", _iso_now())
    new_metadata["updated_at"] = _iso_now()
    new_data["metadata"] = new_metadata

    return new_data, changed


@app.get("/api/stories/{story_generation_id}/assembly")
async def get_or_create_assembly(
    story_generation_id: str,
    force_hydrate: bool = Query(False, description="Force re-hydrating slide content from DB story sources"),
):
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
        # Hydrate existing assembly content from canonical story tables.
        # This fixes older saved assemblies that contain placeholder test content.
        story_data = get_story_full_data(story_generation_id)
        if not story_data:
            raise HTTPException(status_code=404, detail="Story not found")

        hydrated_data, changed = hydrate_assembly_from_story(
            existing["assembly_data"] or {},
            story_data,
            force=force_hydrate,
        )

        return {
            "assembly": {
                "id": str(existing["id"]),
                "story_generation_id": str(existing["story_generation_id"]),
                "assembly_data": hydrated_data,
                "status": existing["status"],
                "created_at": existing["created_at"],
                "updated_at": existing["updated_at"],
            },
            # Treat hydration like a "new default" so the editor shows unsaved changes.
            "is_default": bool(changed),
        }
    
    # Generate default assembly
    story_data = get_story_full_data(story_generation_id)
    if not story_data:
        raise HTTPException(status_code=404, detail="Story not found")
    
    default_assembly = generate_default_assembly(story_data)
    # Mark as hydrated so subsequent loads don't overwrite manual edits.
    default_assembly.setdefault("metadata", {})
    default_assembly["metadata"]["hydrated_from_story"] = True
    default_assembly["metadata"]["hydrated_at"] = _iso_now()
    
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
# Template Rendering Endpoint
# =============================================================================

@app.get("/api/render/{template_type}")
async def render_template(
    template_type: str,
    slide_id: str = Query(..., description="Slide ID for postMessage identification"),
    slide_type: str = Query("text", description="Slide type: cover, text, photo")
):
    """
    Serve a template with the wrapper script injected.
    
    The wrapper script enables postMessage communication between
    the template iframe and the parent editor.
    
    Template types: cover3, editorial3, photos1, closing1
    """
    # Map template type to file
    template_files = {
        "cover3": "cover3.html",
        "editorial3": "editorial3.html",
        "photos1": "photos1.html",
        "videos1": "videos1.html",
        "closing1": "closing1.html",
    }
    
    if template_type not in template_files:
        raise HTTPException(status_code=400, detail=f"Unknown template type: {template_type}")
    
    template_path = os.path.join(config.TEMPLATE_DESIGN_DIR, 'chosen_templates', template_files[template_type])
    
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail=f"Template not found: {template_type}")
    
    # Read the template
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # Fix image paths to use our served assets
    # Original: ../img/... → /template-assets/img/...
    html = html.replace('src="../img/', 'src="/template-assets/img/')
    html = html.replace("src='../img/", "src='/template-assets/img/")
    
    # Cache-bust the wrapper script so UI changes apply immediately in iframes.
    wrapper_path = os.path.join(config.STATIC_DIR, "js", "template-wrapper.js")
    wrapper_v = None
    try:
        wrapper_v = str(int(os.path.getmtime(wrapper_path)))
    except Exception:
        wrapper_v = str(int(datetime.now().timestamp()))

    wrapper_src = f"/static/js/template-wrapper.js?v={wrapper_v}"

    # Create the initialization script with slide metadata
    init_script = f'''
<script>
  // Set slide metadata before wrapper script runs
  window.__slideId = "{slide_id}";
  window.__slideType = "{slide_type}";
</script>
<script src="{wrapper_src}"></script>
'''
    
    # Inject the wrapper script before </body>
    if '</body>' in html:
        html = html.replace('</body>', f'{init_script}</body>')
    else:
        # Fallback: append to end
        html += init_script
    
    return HTMLResponse(
        content=html,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


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
    try:
        from .db import get_db_connection
    except ImportError:
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


@app.get("/api/debug/db")
async def debug_db():
    """
    Non-sensitive DB fingerprint to confirm which DB this API is connected to.
    """
    return get_db_fingerprint()


@app.get("/api/debug/story/{story_generation_id}")
async def debug_story(story_generation_id: str):
    """
    Lightweight debug endpoint to confirm caption/hashtags presence for a story id.
    """
    row = get_story_caption_and_hashtags(story_generation_id)
    if not row:
        raise HTTPException(status_code=404, detail="Story generation not found")

    caption = row.get("instagram_caption")
    hashtags = row.get("hashtags") or []

    return {
        "story_generation_id": str(row.get("story_generation_id")),
        "created_at": row.get("created_at"),
        "has_caption": bool(caption and str(caption).strip()),
        "caption_len": len(str(caption)) if caption is not None else 0,
        "hashtag_count": len(hashtags) if isinstance(hashtags, list) else None,
        "hashtags_type": type(hashtags).__name__,
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
    generations = story_data.get("generations") or []
    gm = (story.get("generation_metadata") or {}) if isinstance(story.get("generation_metadata"), dict) else {}
    default_selected_option_id = gm.get("selected_id")
    selected_gen_id = (
        str(default_selected_option_id) if default_selected_option_id is not None else None
    ) or (str(generations[0].get("id")) if generations else None)
    selected_gen = next((g for g in generations if str(g.get("id")) == str(selected_gen_id)), None)
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
            "title": (selected_gen or {}).get("hook_title") or story['hook_title'],
            "subtitle": (selected_gen or {}).get("subtitle") or story['subtitle'],
            "thumbnail_url": selected_thumb['image_url'] if selected_thumb else None,
            # Non-destructive "crop" controls for the cover background image
            "thumbnail_zoom": 1.0,
            "thumbnail_offset_x": 0.0,
            "thumbnail_offset_y": 0.0,
            "domain_tag": (selected_gen or {}).get("domain_tag") or story['domain_tag']
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

    # 4. Closing slide (always last)
    # It renders primary sources from story_research; if none exist, the section is hidden client-side.
    assembly_slides.append({
        "id": str(uuid.uuid4()),
        "type": SlideType.TEXT.value,
        "template": TemplateType.CLOSING1.value,
        "visible": True,
        "content": {
            "primary_sources": story.get("primary_sources") or [],
            "primary_source_urls": story.get("primary_source_urls") or [],
            "domain_tag": story.get("domain_tag"),
        },
    })
    
    return {
        "version": 1,
        "story_generation_id": str(story['story_generation_id']),
        "selected_generation_id": selected_gen_id,
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

