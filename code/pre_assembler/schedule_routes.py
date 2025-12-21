"""
Schedule routes for the Pre-Assembler API.
Integrates the scheduler functionality into the main app.
"""

import os
import sys
import logging
import base64
import time
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from enum import Enum

# Add scheduler to path for imports
scheduler_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scheduler")
if scheduler_path not in sys.path:
    sys.path.insert(0, scheduler_path)

from scheduler.schedule_db import (
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
    save_rendered_slides,
    get_posts_needing_render,
    debug_scheduler_state,
    update_scheduled_post_assembly,
    update_assembly_data,
)
from scheduler.render import render_assembly_to_png_bytes
from scheduler.storage import upload_bytes_to_supabase
from scheduler.config import config as scheduler_config

from .db import get_story_full_data
from .hydration import hydrate_assembly_from_story

logger = logging.getLogger(__name__)

# Small in-process cache for rendered preview PNG data URLs.
# Keyed by (assembly_id + assembly_updated_at) so edits invalidate naturally.
_PREVIEW_RENDER_CACHE: dict[str, tuple[float, list[dict]]] = {}
_PREVIEW_RENDER_CACHE_TTL_S = 10 * 60
_PREVIEW_RENDER_CACHE_MAX = 32


async def _render_and_store_for_post(
    *,
    post_id: str,
    story_id: str,
    assembly_id: str,
    assembly_data: dict,
) -> list[dict]:
    """
    Render the assembly to PNGs, upload to Supabase Storage, and persist `rendered_slides`
    into the specific assembly row.
    Returns the rendered_slides payload.
    """
    # Hydrate before rendering so edits stored in story tables are reflected.
    story_data = get_story_full_data(story_id)
    if story_data:
        hydrated, changed = hydrate_assembly_from_story(assembly_data, story_data, force=False)
        if changed and assembly_id:
            update_assembly_data(assembly_id=assembly_id, assembly_data=hydrated)
            assembly_data = hydrated

    # Keep scheduled_posts pointing at the rendered assembly_id (for UI display)
    if post_id and assembly_id:
        update_scheduled_post_assembly(post_id=post_id, assembly_id=assembly_id)

    rendered = await render_assembly_to_png_bytes(assembly_data)
    if not rendered:
        raise ValueError("No visible slides to render")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    object_base = f"story-posts/{story_id}/{timestamp}"

    rendered_slides: list[dict] = []
    for i, slide in enumerate(rendered):
        object_path = f"{object_base}/{slide.filename}"
        url = upload_bytes_to_supabase(
            data=slide.png_bytes,
            content_type="image/png",
            object_path=object_path,
        )
        rendered_slides.append(
            {
                "index": i,
                "filename": slide.filename,
                "public_url": url,
                "sha256": slide.sha256,
            }
        )

    save_rendered_slides(story_id, rendered_slides, assembly_id=assembly_id or None)
    return rendered_slides


async def _render_preview_data_urls(*, cache_key: str, assembly_data: dict, max_slides: int = 10) -> list[dict]:
    """
    Render slides and return data URLs for preview UI (no storage uploads).
    This guarantees the scheduler preview shows the actual assembled carousel.
    """
    # Cache check (TTL-based). We key by post_id (caller provides cache_key).
    now = time.time()
    hit = _PREVIEW_RENDER_CACHE.get(cache_key)
    if hit and (now - hit[0]) <= _PREVIEW_RENDER_CACHE_TTL_S:
        return hit[1]

    rendered = await render_assembly_to_png_bytes(assembly_data)
    if not rendered:
        return []
    rendered = rendered[: max(1, int(max_slides))]
    slides: list[dict] = []
    for i, slide in enumerate(rendered):
        b64 = base64.b64encode(slide.png_bytes).decode("utf-8")
        slides.append(
            {
                "index": i,
                "type": "rendered",
                "template": "",
                "thumbnail_url": f"data:image/png;base64,{b64}",
                "text_preview": None,
                "title": None,
                "filename": slide.filename,
            }
        )

    # Cache insert (simple eviction)
    _PREVIEW_RENDER_CACHE[cache_key] = (now, slides)
    if len(_PREVIEW_RENDER_CACHE) > _PREVIEW_RENDER_CACHE_MAX:
        # drop oldest
        oldest_key = min(_PREVIEW_RENDER_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _PREVIEW_RENDER_CACHE.pop(oldest_key, None)
    return slides

# =============================================================================
# Models
# =============================================================================

class ScheduleStatus(str, Enum):
    SCHEDULED = "scheduled"
    APPROVED = "approved"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"


class ScheduledPostSummary(BaseModel):
    id: str
    story_generation_id: str
    assembly_id: Optional[str] = None
    hook_title: str
    subtitle: Optional[str] = None
    domain_tag: Optional[str] = None
    thumbnail_url: Optional[str] = None
    scheduled_at: datetime
    position: int
    status: ScheduleStatus
    approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    instagram_media_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime


class ScheduleResponse(BaseModel):
    posts: list[ScheduledPostSummary]
    count: int
    pending_count: int
    approved_count: int
    published_count: int
    failed_count: int


class SyncScheduleResponse(BaseModel):
    added: int
    already_scheduled: int
    schedule: list[ScheduledPostSummary]


class UpdateScheduledPostRequest(BaseModel):
    scheduled_at: Optional[datetime] = None
    position: Optional[int] = None


class MovePostRequest(BaseModel):
    new_position: int


class ApproveScheduleResponse(BaseModel):
    approved_count: int
    approval_id: str


class TokenStatus(BaseModel):
    has_token: bool
    expires_at: Optional[datetime] = None
    days_until_expiry: Optional[float] = None
    is_healthy: bool
    needs_refresh: bool


# =============================================================================
# Router
# =============================================================================

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


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


@router.get("", response_model=ScheduleResponse)
async def list_schedule(
    include_published: bool = Query(True),
    include_failed: bool = Query(True),
    limit: int = Query(100),
):
    """Get the current posting schedule."""
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


@router.post("/sync", response_model=SyncScheduleResponse)
async def sync_schedule():
    """Find newly approved stories and add them to the schedule."""
    new_stories = get_approved_stories_not_scheduled()
    
    added = 0
    existing_slots = []
    
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
            logger.error(f"Failed to schedule story {story['story_generation_id']}: {e}")
    
    rows = get_scheduled_posts()
    posts = [_row_to_summary(row) for row in rows]
    
    return SyncScheduleResponse(
        added=added,
        already_scheduled=len(new_stories) - added,
        schedule=posts,
    )


@router.patch("/{post_id}")
async def update_post(post_id: str, request: UpdateScheduledPostRequest):
    """Update a scheduled post's time or position."""
    updated = update_scheduled_post(
        post_id,
        scheduled_at=request.scheduled_at,
        position=request.position,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Post not found")
    return _row_to_summary(updated)


@router.delete("/{post_id}")
async def remove_post(post_id: str):
    """Remove a post from the schedule."""
    deleted = delete_scheduled_post(post_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"success": True, "message": "Post removed from schedule"}


@router.post("/{post_id}/move")
async def move_post(post_id: str, request: MovePostRequest):
    """Reorder a post in the schedule."""
    try:
        rows = reorder_schedule(post_id, request.new_position)
        posts = [_row_to_summary(row) for row in rows]
        return {"schedule": posts}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{post_id}/retry")
async def retry_post(post_id: str):
    """Retry a failed post by resetting its status to 'approved'."""
    post = get_scheduled_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post["status"] != "failed":
        raise HTTPException(status_code=400, detail="Post is not in failed status")
    updated = update_scheduled_post(post_id, status="approved")
    return _row_to_summary(updated)


@router.post("/approve", response_model=ApproveScheduleResponse)
async def approve_all(auto_render: bool = True):
    """
    Approve all 'scheduled' posts for auto-posting.
    Also renders slides and uploads to Supabase Storage.
    """
    count, approval_id = approve_schedule()
    
    if count == 0:
        return ApproveScheduleResponse(approved_count=0, approval_id="")
    
    # Auto-render approved posts
    if auto_render:
        logger.info(f"Auto-rendering {count} approved posts...")
        posts = get_posts_needing_render()
        
        for post in posts:
            story_id = str(post["story_generation_id"])
            post_id = str(post.get("post_id") or "")
            assembly_id = str(post.get("assembly_id") or "")
            assembly_data = post.get("assembly_data") or {}
            
            try:
                rendered_slides = await _render_and_store_for_post(
                    post_id=post_id,
                    story_id=story_id,
                    assembly_id=assembly_id,
                    assembly_data=assembly_data,
                )
                logger.info(f"Rendered {len(rendered_slides)} slides for {story_id}")
            except Exception as e:
                logger.error(f"Auto-render failed for {story_id}: {e}")
    
    return ApproveScheduleResponse(approved_count=count, approval_id=approval_id)


@router.post("/{post_id}/render")
async def render_post(post_id: str):
    """
    Render a scheduled post into slide PNGs, upload them to Supabase Storage,
    and store the resulting URLs in the assembly JSON.
    """
    post = get_scheduled_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    story_id = str(post["story_generation_id"])
    assembly = get_assembly_for_post(story_id)
    if not assembly:
        raise HTTPException(status_code=404, detail="Assembly not found")

    assembly_id = str(assembly.get("id") or "")
    assembly_data = assembly.get("assembly_data") or {}

    try:
        rendered_slides = await _render_and_store_for_post(
            post_id=str(post_id),
            story_id=story_id,
            assembly_id=assembly_id,
            assembly_data=assembly_data,
        )
        return {
            "post_id": str(post_id),
            "story_generation_id": story_id,
            "assembly_id": assembly_id,
            "slide_count": len(rendered_slides),
            "slides": rendered_slides,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render failed: {str(e)}")


@router.get("/{post_id}/preview")
async def get_post_preview(post_id: str):
    """Get preview data for a scheduled post."""
    post = get_scheduled_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    story_id = str(post["story_generation_id"])
    assembly = get_assembly_for_post(story_id)
    if not assembly:
        raise HTTPException(status_code=404, detail="Assembly not found")
    
    assembly_data = assembly.get("assembly_data") or {}

    # Hydrate preview from canonical story tables so edits always show up.
    story_data = get_story_full_data(story_id)
    if story_data:
        hydrated, _changed = hydrate_assembly_from_story(assembly_data, story_data, force=False)
        assembly_data = hydrated

    # If we already have rendered slides, use those as the preview (most faithful).
    rendered_slides = assembly_data.get("rendered_slides") or []
    render_mode = "fallback"
    render_error = None

    if isinstance(rendered_slides, list) and len(rendered_slides) > 0:
        slides = []
        for s in rendered_slides:
            if not isinstance(s, dict):
                continue
            slides.append(
                {
                    "index": int(s.get("index") or 0),
                    "type": "rendered",
                    "template": "",
                    "thumbnail_url": s.get("public_url"),
                    "text_preview": None,
                    "title": None,
                    "filename": s.get("filename"),
                }
            )
        slides.sort(key=lambda x: x.get("index", 0))
        render_mode = "stored_urls"
    else:
        # Render on-demand for preview as in-memory PNG data URLs (no uploads).
        # This ensures the preview shows the actual assembled post even if storage is unavailable.
        try:
            slides = await _render_preview_data_urls(
                cache_key=f"post:{post_id}:max10",
                assembly_data=assembly_data,
                max_slides=10,
            )
            render_mode = "in_memory_png"
        except Exception:
            # Fallback: show structured slide meta (cover/photo thumbs + text excerpts)
            import traceback
            render_error = traceback.format_exc()[-1200:]
            slides_data = assembly_data.get("slides") or []
            slides = []
            for i, slide in enumerate(slides_data):
                if not isinstance(slide, dict) or not slide.get("visible", True):
                    continue
                content = slide.get("content") or {}
                slides.append(
                    {
                        "index": i,
                        "type": slide.get("type", "text"),
                        "template": slide.get("template", ""),
                        "thumbnail_url": content.get("thumbnail_url") or content.get("image_url"),
                        "text_preview": (content.get("text", "")[:140] + "...") if content.get("text") else None,
                        "title": content.get("title"),
                    }
                )
    
    hashtags = assembly.get("hashtags") or []
    if isinstance(hashtags, str):
        hashtags = hashtags.split()
    
    return {
        "story_generation_id": story_id,
        "hook_title": post.get("hook_title", "Untitled"),
        "subtitle": post.get("subtitle"),
        "caption": assembly.get("instagram_caption"),
        "hashtags": hashtags,
        "slide_count": len(slides),
        "slides": slides,
        "render_mode": render_mode,
        "render_error": render_error,
    }


# Token status endpoint
@router.get("/tokens/status", response_model=TokenStatus)
async def get_token_status():
    """Get the current token's health status."""
    token = get_active_token()
    
    if not token:
        return TokenStatus(has_token=False, is_healthy=False, needs_refresh=True)
    
    now = datetime.now(ZoneInfo("UTC"))
    expires_at = token.get("expires_at")
    
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=ZoneInfo("UTC"))
        days_until = (expires_at - now).total_seconds() / 86400
        is_healthy = days_until > 7
        needs_refresh = days_until <= 7
    else:
        days_until = None
        is_healthy = True
        needs_refresh = False
    
    return TokenStatus(
        has_token=True,
        expires_at=expires_at,
        days_until_expiry=round(days_until, 1) if days_until is not None else None,
        is_healthy=is_healthy,
        needs_refresh=needs_refresh,
    )


@router.get("/debug/state")
async def debug_state():
    """
    Debug endpoint to confirm scheduler DB connectivity + why eligibility might be 0.
    """
    return debug_scheduler_state()

