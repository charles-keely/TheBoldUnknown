import asyncio
import hashlib
import logging
import os
import re
import base64
from dataclasses import dataclass

from assembler.builder import SlideBuilder
from assembler.renderer import Renderer

from scheduler.db import get_thumbnail_source

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderedSlide:
    filename: str
    png_bytes: bytes
    sha256: str


def _normalize_assembly(assembly_data: dict) -> dict:
    """
    Accept either:
    - raw assembly_data object
    - wrapper with {"assembly_data": {...}}
    """
    if not assembly_data:
        return {}
    if "slides" in assembly_data:
        return assembly_data
    if isinstance(assembly_data.get("assembly_data"), dict):
        return assembly_data["assembly_data"]
    return assembly_data


_THUMB_API_RE = re.compile(r"^/api/thumbnails/(?P<id>[0-9a-fA-F-]{36})/image$")


def _resolve_internal_thumbnail_url(url: str) -> str | None:
    """
    Convert internal Pre-Assembler thumbnail endpoint paths into something renderable:
    - Prefer story_thumbnails.image_url if present (public URL)
    - Else use generation_metadata.image_base64 -> data: URL
    """
    if not url or not isinstance(url, str):
        return None
    m = _THUMB_API_RE.match(url.strip())
    if not m:
        return None

    tid = m.group("id")
    src = get_thumbnail_source(thumbnail_id=tid)
    if not src:
        return None

    image_url = src.get("image_url")
    if isinstance(image_url, str) and image_url.startswith(("http://", "https://", "data:")):
        return image_url

    b64 = src.get("image_base64")
    if isinstance(b64, str) and b64.strip():
        mime = src.get("mime_type") or "image/png"
        # Ensure it's raw base64 without data: prefix
        raw = b64.strip()
        if raw.startswith("data:"):
            return raw
        return f"data:{mime};base64,{raw}"

    return None


async def render_assembly_to_png_bytes(assembly_data: dict) -> list[RenderedSlide]:
    """
    Render visible slides to PNG bytes.
    This does NOT write to disk and does NOT touch the database.
    """
    data = _normalize_assembly(assembly_data)
    slides = data.get("slides") or []
    if not slides:
        return []

    builder = SlideBuilder(working_dir=None)
    rendered: list[RenderedSlide] = []

    async with Renderer() as renderer:
        visible_slides = [s for s in slides if isinstance(s, dict) and s.get("visible", True)]
        total = len(visible_slides)
        for idx, slide in enumerate(visible_slides):
            # Patch internal Pre-Assembler thumbnail URLs into renderable sources
            # so cover backgrounds render correctly in Playwright.
            s = dict(slide)
            content = dict((s.get("content") or {})) if isinstance(s.get("content"), dict) else {}
            for key in ("thumbnail_url", "image_url"):
                v = content.get(key)
                if isinstance(v, str) and v.startswith("/api/thumbnails/"):
                    resolved = _resolve_internal_thumbnail_url(v)
                    if resolved:
                        content[key] = resolved
            s["content"] = content

            html = builder.build_slide(s, idx, total_slides=total)
            png = await renderer.render_png_bytes(html)
            filename = f"{idx+1:02d}_{slide.get('type') or 'slide'}.png"
            rendered.append(
                RenderedSlide(
                    filename=filename,
                    png_bytes=png,
                    sha256=hashlib.sha256(png).hexdigest(),
                )
            )

    return rendered


def render_assembly_to_png_bytes_sync(assembly_data: dict) -> list[RenderedSlide]:
    return asyncio.run(render_assembly_to_png_bytes(assembly_data))


def ensure_local_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


