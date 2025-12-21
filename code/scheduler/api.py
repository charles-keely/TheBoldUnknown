"""
Scheduler FastAPI Application

A web-based tool for managing the Instagram posting schedule.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import config
from .models import (
    ScheduleStatus,
    ScheduledPostSummary,
    ScheduleResponse,
    SyncScheduleResponse,
    UpdateScheduledPostRequest,
    MovePostRequest,
    MovePostResponse,
    ApproveScheduleResponse,
    DeletePostResponse,
    TokenStatus,
    RefreshTokenResponse,
    PostPreviewResponse,
    SlidePreview,
)
from .schedule_db import (
    get_scheduled_posts,
    get_schedule_counts,
    get_approved_stories_not_scheduled,
    get_next_available_slot,
    add_to_schedule,
    update_scheduled_post,
    get_scheduled_post,
    delete_scheduled_post,
    reorder_schedule,
    approve_schedule,
    get_active_token,
    get_assembly_for_post,
    check_db_connection,
    save_rendered_slides,
    get_posts_needing_render,
)
from .token_refresh import exchange_for_long_lived_token, compute_expires_at
from .render import render_assembly_to_png_bytes_sync
from .storage import upload_bytes_to_supabase


# =============================================================================
# App Setup
# =============================================================================

app = FastAPI(
    title="TheBoldUnknown Scheduler",
    description="Web tool for managing Instagram posting schedule",
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

# Create static dir if it doesn't exist
os.makedirs(config.STATIC_DIR, exist_ok=True)
os.makedirs(os.path.join(config.STATIC_DIR, "js"), exist_ok=True)
os.makedirs(os.path.join(config.STATIC_DIR, "css"), exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

# Mount template design assets (for thumbnail previews)
template_img_dir = os.path.join(config.TEMPLATE_DESIGN_DIR, 'img')
if os.path.exists(template_img_dir):
    app.mount("/template-assets/img", StaticFiles(directory=template_img_dir), name="template-img")


# =============================================================================
# Page Routes
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def schedule_page():
    """Serve the schedule page."""
    index_path = os.path.join(config.STATIC_DIR, 'schedule.html')
    if os.path.exists(index_path):
        return FileResponse(index_path, headers={"Cache-Control": "no-store"})
    return HTMLResponse("<h1>Scheduler</h1><p>schedule.html not found</p>")


# =============================================================================
# API Routes - Schedule
# =============================================================================

def _row_to_summary(row: dict) -> ScheduledPostSummary:
    """Convert a DB row to a ScheduledPostSummary."""
    return ScheduledPostSummary(
        id=str(row["id"]),
        story_generation_id=str(row["story_generation_id"]),
        assembly_id=str(row["assembly_id"]) if row.get("assembly_id") else None,
        hook_title=row.get("hook_title", "Untitled"),
        subtitle=row.get("subtitle"),
        domain_tag=row.get("domain_tag"),
        thumbnail_url=row.get("thumbnail_url"),
        scheduled_at=row["scheduled_at"],
        position=row["position"],
        status=ScheduleStatus(row["status"]),
        approved_at=row.get("approved_at"),
        published_at=row.get("published_at"),
        instagram_media_id=row.get("instagram_media_id"),
        error_message=row.get("error_message"),
        retry_count=row.get("retry_count", 0),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@app.get("/api/schedule", response_model=ScheduleResponse)
async def list_schedule(
    include_published: bool = Query(True, description="Include published posts"),
    include_failed: bool = Query(True, description="Include failed posts"),
    limit: int = Query(100, description="Maximum number of posts to return"),
):
    """
    Get the current posting schedule.
    Returns posts ordered by scheduled time.
    """
    rows = get_scheduled_posts(
        include_published=include_published,
        include_failed=include_failed,
        limit=limit,
    )
    counts = get_schedule_counts()
    
    posts = [_row_to_summary(row) for row in rows]
    
    return ScheduleResponse(
        posts=posts,
        count=len(posts),
        pending_count=counts["pending_count"],
        approved_count=counts["approved_count"],
        published_count=counts["published_count"],
        failed_count=counts["failed_count"],
    )


@app.post("/api/schedule/sync", response_model=SyncScheduleResponse)
async def sync_schedule():
    """
    Find newly approved stories and add them to the schedule.
    Assigns next available time slots (8:30 AM, 1:00 PM, 7:00 PM MST).
    """
    # Get stories that need scheduling
    new_stories = get_approved_stories_not_scheduled()
    
    added = 0
    existing_slots = []  # Track slots as we add them
    
    for story in new_stories:
        slot = get_next_available_slot(existing_slots)
        try:
            add_to_schedule(
                story_generation_id=str(story["story_generation_id"]),
                assembly_id=str(story["assembly_id"]),
                scheduled_at=slot,
            )
            existing_slots.append(slot)
            added += 1
        except Exception as e:
            # Log but continue with other stories
            import logging
            logging.error(f"Failed to schedule story {story['story_generation_id']}: {e}")
    
    # Get updated schedule
    rows = get_scheduled_posts()
    posts = [_row_to_summary(row) for row in rows]
    
    return SyncScheduleResponse(
        added=added,
        already_scheduled=len(new_stories) - added,
        schedule=posts,
    )


@app.patch("/api/schedule/{post_id}")
async def update_post(post_id: str, request: UpdateScheduledPostRequest):
    """
    Update a scheduled post's time or position.
    """
    updated = update_scheduled_post(
        post_id,
        scheduled_at=request.scheduled_at,
        position=request.position,
    )
    
    if not updated:
        raise HTTPException(status_code=404, detail="Post not found")
    
    return _row_to_summary(updated)


@app.delete("/api/schedule/{post_id}", response_model=DeletePostResponse)
async def remove_post(post_id: str):
    """
    Remove a post from the schedule.
    """
    deleted = delete_scheduled_post(post_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found")
    
    return DeletePostResponse(success=True, message="Post removed from schedule")


@app.post("/api/schedule/{post_id}/move", response_model=MovePostResponse)
async def move_post(post_id: str, request: MovePostRequest):
    """
    Reorder a post in the schedule.
    """
    try:
        rows = reorder_schedule(post_id, request.new_position)
        posts = [_row_to_summary(row) for row in rows]
        return MovePostResponse(schedule=posts)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/schedule/{post_id}/retry")
async def retry_post(post_id: str):
    """
    Retry a failed post by resetting its status to 'approved'.
    """
    post = get_scheduled_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post["status"] != "failed":
        raise HTTPException(status_code=400, detail="Post is not in failed status")
    
    # Reset to approved with retry count reset
    updated = update_scheduled_post(post_id, status="approved")
    return _row_to_summary(updated)


@app.post("/api/schedule/approve", response_model=ApproveScheduleResponse)
async def approve_all(auto_render: bool = True):
    """
    Approve all 'scheduled' posts for auto-posting.
    Sets status='approved' and approved_at=NOW().
    
    By default, also renders slides and uploads to Supabase Storage
    so the Cloudflare worker can publish without manual steps.
    """
    import logging
    from datetime import datetime, timezone
    
    logger = logging.getLogger(__name__)
    
    count, approval_id = approve_schedule()
    
    if count == 0:
        return ApproveScheduleResponse(
            approved_count=0,
            approval_id="",
        )
    
    # Auto-render approved posts
    if auto_render:
        logger.info(f"Auto-rendering {count} approved posts...")
        posts = get_posts_needing_render()
        
        for post in posts:
            story_id = str(post["story_generation_id"])
            assembly_data = post.get("assembly_data") or {}
            
            try:
                rendered = render_assembly_to_png_bytes_sync(assembly_data)
                
                if not rendered:
                    logger.warning(f"No visible slides for {story_id}")
                    continue
                
                # Upload to Supabase Storage
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                object_base = f"story-posts/{story_id}/{timestamp}"
                
                rendered_slides = []
                for i, slide in enumerate(rendered):
                    object_path = f"{object_base}/{slide.filename}"
                    url = upload_bytes_to_supabase(
                        data=slide.png_bytes,
                        content_type="image/png",
                        object_path=object_path,
                    )
                    rendered_slides.append({
                        "index": i,
                        "filename": slide.filename,
                        "public_url": url,
                        "sha256": slide.sha256,
                    })
                
                # Save rendered URLs to assembly_data
                save_rendered_slides(story_id, rendered_slides)
                logger.info(f"Rendered and uploaded {len(rendered_slides)} slides for {story_id}")
                
            except Exception as e:
                logger.error(f"Auto-render failed for {story_id}: {e}")
                # Continue with other posts - don't fail the whole approval
    
    return ApproveScheduleResponse(
        approved_count=count,
        approval_id=approval_id,
    )


# =============================================================================
# API Routes - Token Management
# =============================================================================

@app.get("/api/tokens/status", response_model=TokenStatus)
async def get_token_status():
    """
    Get the current token's health status.
    """
    token = get_active_token()
    
    if not token:
        return TokenStatus(
            has_token=False,
            is_healthy=False,
            needs_refresh=True,
        )
    
    now = datetime.now(ZoneInfo("UTC"))
    expires_at = token.get("expires_at")
    
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=ZoneInfo("UTC"))
        
        days_until = (expires_at - now).total_seconds() / 86400
        is_healthy = days_until > 7  # Healthy if > 7 days remaining
        needs_refresh = days_until <= 7
    else:
        days_until = None
        is_healthy = True  # Assume healthy if no expiry set
        needs_refresh = False
    
    return TokenStatus(
        has_token=True,
        expires_at=expires_at,
        days_until_expiry=round(days_until, 1) if days_until is not None else None,
        is_healthy=is_healthy,
        needs_refresh=needs_refresh,
        last_used_at=token.get("last_used_at"),
    )


@app.post("/api/tokens/refresh", response_model=RefreshTokenResponse)
async def refresh_token():
    """
    Manually trigger a token refresh.
    Uses the existing token to exchange for a new long-lived token.
    """
    token = get_active_token()
    
    if not token:
        return RefreshTokenResponse(
            success=False,
            message="No active token found. Please set up a token first.",
        )
    
    if not config.META_APP_ID or not config.META_APP_SECRET:
        return RefreshTokenResponse(
            success=False,
            message="META_APP_ID and META_APP_SECRET are required for token refresh.",
        )
    
    try:
        from .schedule_db import save_new_token
        import time
        
        resp = exchange_for_long_lived_token(
            graph_api_version=config.GRAPH_API_VERSION,
            app_id=config.META_APP_ID,
            app_secret=config.META_APP_SECRET,
            fb_exchange_token=token["access_token"],
        )
        
        new_token = resp.get("access_token")
        expires_in = resp.get("expires_in")
        
        if not new_token:
            return RefreshTokenResponse(
                success=False,
                message=f"Token exchange failed: {resp}",
            )
        
        # Calculate new expiry
        now = int(time.time())
        expires_at_ts = compute_expires_at(expires_in=expires_in, now=now)
        expires_at = datetime.fromtimestamp(expires_at_ts, ZoneInfo("UTC")) if expires_at_ts else None
        
        # Save new token
        save_new_token(
            access_token=new_token,
            expires_at=expires_at,
            token_type=resp.get("token_type", "bearer"),
        )
        
        return RefreshTokenResponse(
            success=True,
            message="Token refreshed successfully",
            new_expires_at=expires_at,
        )
    except Exception as e:
        return RefreshTokenResponse(
            success=False,
            message=f"Token refresh failed: {str(e)}",
        )


# =============================================================================
# API Routes - Post Preview
# =============================================================================

@app.get("/api/schedule/{post_id}/preview", response_model=PostPreviewResponse)
async def get_post_preview(post_id: str):
    """
    Get preview data for a scheduled post.
    """
    post = get_scheduled_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Get assembly data
    assembly = get_assembly_for_post(str(post["story_generation_id"]))
    if not assembly:
        raise HTTPException(status_code=404, detail="Assembly not found")
    
    assembly_data = assembly.get("assembly_data") or {}
    slides_data = assembly_data.get("slides") or []
    
    slides = []
    for i, slide in enumerate(slides_data):
        if not isinstance(slide, dict):
            continue
        
        content = slide.get("content") or {}
        slide_type = slide.get("type", "text")
        
        # Get thumbnail/image URL for cover/photo slides
        thumbnail_url = None
        if slide_type == "cover":
            thumbnail_url = content.get("thumbnail_url")
        elif slide_type == "photo":
            thumbnail_url = content.get("image_url")
        
        # Get text preview
        text_preview = None
        if slide_type == "text":
            text = content.get("text", "")
            if text:
                text_preview = text[:100] + "..." if len(text) > 100 else text
        
        slides.append(SlidePreview(
            index=i,
            type=slide_type,
            template=slide.get("template", ""),
            visible=slide.get("visible", True),
            thumbnail_url=thumbnail_url,
            text_preview=text_preview,
        ))
    
    # Get hashtags
    hashtags = assembly.get("hashtags") or []
    if isinstance(hashtags, str):
        hashtags = hashtags.split()
    
    return PostPreviewResponse(
        story_generation_id=str(post["story_generation_id"]),
        hook_title=post.get("hook_title", "Untitled"),
        subtitle=post.get("subtitle"),
        caption=assembly.get("instagram_caption"),
        hashtags=hashtags,
        slide_count=len([s for s in slides if s.visible]),
        slides=slides,
    )


# =============================================================================
# API Routes - Thumbnails (proxy to pre_assembler style)
# =============================================================================

@app.get("/api/thumbnails/{thumbnail_id}/image")
async def get_thumbnail_image(thumbnail_id: str):
    """
    Serve thumbnail image from database.
    Same logic as pre_assembler.
    """
    from fastapi.responses import Response
    from .schedule_db import get_db_connection
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
            
            if not row or not row.get('generation_metadata'):
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
                headers={"Cache-Control": "public, max-age=86400"}
            )
    finally:
        conn.close()


# =============================================================================
# API Routes - Rendering
# =============================================================================

@app.post("/api/schedule/{post_id}/render")
async def render_post(post_id: str):
    """
    Render slides for a scheduled post and upload to Supabase Storage.
    Returns the public URLs for the rendered slides.
    
    This should be called before the worker attempts to publish.
    """
    import logging
    from datetime import datetime, timezone
    
    logger = logging.getLogger(__name__)
    
    # Get the post
    post = get_scheduled_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Get assembly data
    assembly = get_assembly_for_post(str(post["story_generation_id"]))
    if not assembly:
        raise HTTPException(status_code=404, detail="Assembly not found")
    
    assembly_data = assembly.get("assembly_data") or {}
    
    # Render slides
    try:
        rendered = render_assembly_to_png_bytes_sync(assembly_data)
    except Exception as e:
        logger.error(f"Render failed: {e}")
        raise HTTPException(status_code=500, detail=f"Rendering failed: {str(e)}")
    
    if not rendered:
        raise HTTPException(status_code=400, detail="No visible slides to render")
    
    # Upload to Supabase Storage
    story_id = str(post["story_generation_id"])
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    object_base = f"story-posts/{story_id}/{timestamp}"
    
    rendered_slides = []
    for i, slide in enumerate(rendered):
        object_path = f"{object_base}/{slide.filename}"
        try:
            url = upload_bytes_to_supabase(
                data=slide.png_bytes,
                content_type="image/png",
                object_path=object_path,
            )
            rendered_slides.append({
                "index": i,
                "filename": slide.filename,
                "public_url": url,
                "sha256": slide.sha256,
            })
            logger.info(f"Uploaded {slide.filename} -> {url}")
        except Exception as e:
            logger.error(f"Upload failed for {slide.filename}: {e}")
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    
    # Save rendered URLs to assembly_data
    save_rendered_slides(story_id, rendered_slides)
    
    return {
        "post_id": post_id,
        "story_generation_id": story_id,
        "slide_count": len(rendered_slides),
        "slides": rendered_slides,
    }


@app.post("/api/schedule/render-all")
async def render_all_pending():
    """
    Render all approved posts that haven't been rendered yet.
    Useful to run before deploying the worker.
    """
    import logging
    from datetime import datetime, timezone
    
    logger = logging.getLogger(__name__)
    
    posts = get_posts_needing_render()
    
    if not posts:
        return {"message": "No posts need rendering", "rendered": 0}
    
    rendered_count = 0
    errors = []
    
    for post in posts:
        story_id = str(post["story_generation_id"])
        assembly_data = post.get("assembly_data") or {}
        
        try:
            rendered = render_assembly_to_png_bytes_sync(assembly_data)
            
            if not rendered:
                errors.append({"story_id": story_id, "error": "No visible slides"})
                continue
            
            # Upload to Supabase Storage
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            object_base = f"story-posts/{story_id}/{timestamp}"
            
            rendered_slides = []
            for i, slide in enumerate(rendered):
                object_path = f"{object_base}/{slide.filename}"
                url = upload_bytes_to_supabase(
                    data=slide.png_bytes,
                    content_type="image/png",
                    object_path=object_path,
                )
                rendered_slides.append({
                    "index": i,
                    "filename": slide.filename,
                    "public_url": url,
                    "sha256": slide.sha256,
                })
            
            # Save rendered URLs
            save_rendered_slides(story_id, rendered_slides)
            rendered_count += 1
            logger.info(f"Rendered {len(rendered_slides)} slides for {story_id}")
            
        except Exception as e:
            logger.error(f"Render failed for {story_id}: {e}")
            errors.append({"story_id": story_id, "error": str(e)})
    
    return {
        "message": f"Rendered {rendered_count} posts",
        "rendered": rendered_count,
        "errors": errors,
    }


# =============================================================================
# Health Check
# =============================================================================

@app.get("/api/health")
async def health_check():
    """Check API and database health."""
    db_ok = check_db_connection()
    token = get_active_token()
    
    return {
        "status": "healthy" if db_ok else "unhealthy",
        "database": "connected" if db_ok else "disconnected",
        "token": "active" if token else "missing",
    }


# =============================================================================
# Run
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG
    )

