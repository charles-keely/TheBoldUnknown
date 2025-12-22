"""
Assembly hydration utilities.

Used to ensure an existing assembly's per-slide content stays in sync with the canonical story tables
while preserving slide ordering / visibility / template selection.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from .models import SlideType, TemplateType


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
    - Assemblies may have been saved with placeholder content.
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
        # Non-destructive backfill:
        # Some pipeline runs historically wrote photos without persisting `story_photos.caption`
        # (or created an assembly before captions existed). If the assembly is marked hydrated,
        # we still want to *fill empty fields* from canonical tables without overwriting user edits.
        photos_by_id = {
            str(p["id"]): p
            for p in (story_data.get("photos") or [])
            if isinstance(p, dict) and p.get("id")
        }

        changed = False
        new_data = dict(assembly_data)
        new_slides = []
        for slide in (assembly_data.get("slides") or []):
            if not isinstance(slide, dict):
                new_slides.append(slide)
                continue

            s = dict(slide)
            if s.get("type") != SlideType.PHOTO.value:
                new_slides.append(s)
                continue

            src_id = s.get("source_photo_id")
            if not src_id or str(src_id) not in photos_by_id:
                new_slides.append(s)
                continue

            p = photos_by_id[str(src_id)]
            content = dict(s.get("content") or {})

            # Only backfill when the assembly field is empty/blank.
            desired_url = (p.get("image_url") or "").strip()
            if desired_url and not str(content.get("image_url") or "").strip():
                content["image_url"] = desired_url
                changed = True

            desired_caption = (p.get("caption") or "").strip()
            if desired_caption and not str(content.get("caption") or "").strip():
                content["caption"] = desired_caption
                changed = True

            desired_source = (p.get("source_attribution") or "").strip()
            if desired_source and not str(content.get("source") or "").strip():
                content["source"] = desired_source
                changed = True

            s["content"] = content
            new_slides.append(s)

        if changed:
            new_data["slides"] = new_slides
            new_metadata = dict(metadata)
            new_metadata["hydrated_at"] = _iso_now()
            new_metadata["updated_at"] = _iso_now()
            new_data["metadata"] = new_metadata
            return new_data, True

        return assembly_data, False

    story = story_data.get("story") or {}
    generations = story_data.get("generations") or []

    gm = (story.get("generation_metadata") or {}) if isinstance(story.get("generation_metadata"), dict) else {}
    default_selected_option_id = gm.get("selected_id")

    # Respect a selected title/subtitle option if present in the assembly JSON.
    selected_gen_id = (
        assembly_data.get("selected_generation_id")
        or (str(default_selected_option_id) if default_selected_option_id is not None else None)
        or (str(generations[0].get("id")) if generations else None)
    )
    selected_gen = next((g for g in generations if str(g.get("id")) == str(selected_gen_id)), None)

    story_domain = (selected_gen or {}).get("domain_tag") or story.get("domain_tag")
    story_primary_sources = story.get("primary_sources") or []
    story_primary_source_urls = story.get("primary_source_urls") or []

    slides_by_id = {str(s["id"]): s for s in (story_data.get("slides") or []) if isinstance(s, dict) and s.get("id")}
    photos_by_id = {str(p["id"]): p for p in (story_data.get("photos") or []) if isinstance(p, dict) and p.get("id")}
    thumbs_by_id = {str(t["id"]): t for t in (story_data.get("thumbnails") or []) if isinstance(t, dict) and t.get("id")}

    # Decide selected thumbnail
    selected_thumb_id = (
        assembly_data.get("selected_thumbnail_id")
        or next((str(t["id"]) for t in (story_data.get("thumbnails") or []) if t.get("is_selected")), None)
        or (str(story_data["thumbnails"][0]["id"]) if story_data.get("thumbnails") else None)
    )
    selected_thumb_url = thumbs_by_id.get(selected_thumb_id, {}).get("image_url") if selected_thumb_id else None

    changed = False
    new_data = dict(assembly_data)
    if str(assembly_data.get("selected_generation_id") or "") != str(selected_gen_id or ""):
        changed = True
    new_data["selected_generation_id"] = selected_gen_id
    new_data["selected_thumbnail_id"] = selected_thumb_id

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

        # Ensure domain tag is present
        if story_domain and content.get("domain_tag") != story_domain:
            content["domain_tag"] = story_domain
            changed = True

        if s.get("type") == SlideType.COVER.value:
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

    new_metadata = dict(metadata)
    new_metadata["hydrated_from_story"] = True
    new_metadata["hydrated_at"] = _iso_now()
    new_metadata.setdefault("created_at", _iso_now())
    new_metadata["updated_at"] = _iso_now()
    new_data["metadata"] = new_metadata

    return new_data, changed


