"""
Background render jobs for Pre-Assembler approvals.

Goal:
- When a story is approved_for_assembly, immediately render its assembled slides,
  upload PNGs to Supabase Storage, and store the resulting public URLs into
  the latest story_assemblies.assembly_data as `rendered_slides`.

Why:
- Scheduler previews become instant (no Playwright render needed at view-time)
- Cloudflare worker can publish using the stored public URLs
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .db import get_assembly, get_story_full_data, ensure_default_assembly_exists
from .hydration import hydrate_assembly_from_story

from scheduler.render import render_assembly_to_png_bytes
from scheduler.storage import upload_bytes_to_supabase
from scheduler.schedule_db import save_rendered_slides, update_assembly_data

logger = logging.getLogger(__name__)

# Simple in-process queue/guard
_inflight: set[str] = set()
_lock = asyncio.Lock()
_sem = asyncio.Semaphore(2)  # limit concurrent renders per process


async def enqueue_render_for_story(story_generation_id: str) -> None:
    """
    Fire-and-forget enqueue. Safe to call from FastAPI handlers.
    """
    async with _lock:
        if story_generation_id in _inflight:
            return
        _inflight.add(story_generation_id)

    async def _runner() -> None:
        try:
            async with _sem:
                await render_and_store_assets(story_generation_id)
        except Exception as e:
            logger.error(f"[render_job] failed story={story_generation_id}: {e}")
        finally:
            async with _lock:
                _inflight.discard(story_generation_id)

    asyncio.create_task(_runner())


async def render_and_store_assets(story_generation_id: str) -> None:
    """
    Render + upload + persist rendered_slides for a story_generation_id.
    """
    story_generation_id = str(story_generation_id)
    logger.info(f"[render_job] start story={story_generation_id}")

    # Ensure at least one assembly exists
    await asyncio.to_thread(ensure_default_assembly_exists, story_generation_id)

    assembly = await asyncio.to_thread(get_assembly, story_generation_id)
    if not assembly:
        raise RuntimeError("No assembly found after ensure_default_assembly_exists")

    assembly_id = str(assembly.get("id") or "")
    assembly_data = assembly.get("assembly_data") or {}

    # Hydrate from canonical story tables so edits propagate
    story_data = await asyncio.to_thread(get_story_full_data, story_generation_id)
    if story_data:
        hydrated, changed = hydrate_assembly_from_story(assembly_data, story_data, force=False)
        if changed and assembly_id:
            await asyncio.to_thread(update_assembly_data, assembly_id=assembly_id, assembly_data=hydrated)
            assembly_data = hydrated

    # Render (async Playwright)
    rendered = await render_assembly_to_png_bytes(assembly_data)
    if not rendered:
        raise RuntimeError("No visible slides to render")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    object_base = f"story-posts/{story_generation_id}/{timestamp}"

    rendered_slides: list[dict] = []
    for i, slide in enumerate(rendered):
        object_path = f"{object_base}/{slide.filename}"
        url = await asyncio.to_thread(
            upload_bytes_to_supabase,
            data=slide.png_bytes,
            content_type="image/png",
            object_path=object_path,
        )
        rendered_slides.append(
            {"index": i, "filename": slide.filename, "public_url": url, "sha256": slide.sha256}
        )

    await asyncio.to_thread(
        save_rendered_slides,
        story_generation_id,
        rendered_slides,
        assembly_id=assembly_id or None,
    )

    logger.info(f"[render_job] done story={story_generation_id} slides={len(rendered_slides)}")



