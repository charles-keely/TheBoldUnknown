"""
Batch re-render + re-upload assembled slide PNGs to Supabase Storage.

Use-cases:
- Fix a template/header bug (e.g., wrong domain tag shown in the cover's top-right meta-data)
  for assets already stored in Supabase buckets.
- Re-render only items that have NOT been posted yet (scheduled/approved/publishing/failed).
- Optionally re-render ONLY the cover (index 0) while preserving correct page numbering.

How it works:
- Select target assemblies from Postgres (via scheduler DB connection).
- Fetch the chosen assembly_data (JSON).
- Hydrate from canonical story tables (so domain_tag/title/subtitle updates propagate).
- Render with Playwright (same path used by the scheduler/pre-assembler).
- Upload PNG bytes to Supabase Storage.
- Persist updated `assembly_data["rendered_slides"]` to the assembly row.

Notes:
- By default this writes NEW objects under a timestamped prefix and updates DB URLs.
  Old (incorrect) images remain in the bucket but become unreferenced.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


from scheduler.schedule_db import get_db_connection, save_rendered_slides, update_assembly_data  # noqa: E402
from scheduler.storage import upload_bytes_to_supabase  # noqa: E402
from scheduler.render import render_assembly_to_png_bytes_selected  # noqa: E402
from assembler.renderer import Renderer  # noqa: E402

from pre_assembler.db import get_story_full_data  # noqa: E402
from pre_assembler.hydration import hydrate_assembly_from_story  # noqa: E402


@dataclass(frozen=True)
class Target:
    story_generation_id: str
    assembly_id: str
    reason: str


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _select_targets(*, scope: str, limit: int | None, story_id: str | None) -> list[Target]:
    """
    scope:
    - all-rendered: chosen assembly per story where rendered_slides already exists
    - not-posted: assemblies referenced by non-published scheduled_posts (or chosen assembly fallback)
    - story: single story_generation_id (debug)
    """
    if scope not in ("all-rendered", "not-posted", "story"):
        raise ValueError(f"Unknown scope: {scope}")

    if scope == "story":
        if not story_id:
            raise ValueError("--story-id is required when --scope=story")
        # Choose finalized-first per story, then latest
        sql = """
        WITH chosen_assembly AS (
          SELECT DISTINCT ON (sa.story_generation_id)
            sa.story_generation_id,
            sa.id as assembly_id,
            sa.assembly_data,
            sa.status,
            sa.updated_at
          FROM story_assemblies sa
          WHERE sa.story_generation_id = %s::uuid
            AND sa.assembly_data IS NOT NULL
          ORDER BY
            sa.story_generation_id,
            CASE WHEN sa.status = 'finalized' THEN 0 ELSE 1 END,
            sa.updated_at DESC
        )
        SELECT story_generation_id::text, assembly_id::text
        FROM chosen_assembly
        LIMIT 1
        """
        params = (story_id,)
    elif scope == "all-rendered":
        sql = """
        WITH chosen_assembly AS (
          SELECT DISTINCT ON (sa.story_generation_id)
            sa.story_generation_id,
            sa.id as assembly_id,
            sa.assembly_data,
            sa.status,
            sa.updated_at
          FROM story_assemblies sa
          WHERE sa.assembly_data IS NOT NULL
          ORDER BY
            sa.story_generation_id,
            CASE WHEN sa.status = 'finalized' THEN 0 ELSE 1 END,
            sa.updated_at DESC
        )
        SELECT ca.story_generation_id::text, ca.assembly_id::text
        FROM chosen_assembly ca
        WHERE ca.assembly_data->'rendered_slides' IS NOT NULL
          AND jsonb_typeof(ca.assembly_data->'rendered_slides') = 'array'
          AND jsonb_array_length(ca.assembly_data->'rendered_slides') > 0
        ORDER BY ca.story_generation_id
        """
        params = ()
    else:  # not-posted
        sql = """
        WITH chosen_assembly AS (
          SELECT DISTINCT ON (sa.story_generation_id)
            sa.story_generation_id,
            sa.id as assembly_id,
            sa.assembly_data,
            sa.status,
            sa.updated_at
          FROM story_assemblies sa
          WHERE sa.assembly_data IS NOT NULL
          ORDER BY
            sa.story_generation_id,
            CASE WHEN sa.status = 'finalized' THEN 0 ELSE 1 END,
            sa.updated_at DESC
        )
        SELECT
          sp.story_generation_id::text as story_generation_id,
          COALESCE(sp.assembly_id, ca.assembly_id)::text as assembly_id,
          sp.status as status
        FROM scheduled_posts sp
        LEFT JOIN chosen_assembly ca ON ca.story_generation_id = sp.story_generation_id
        WHERE sp.status <> 'published'
        ORDER BY sp.scheduled_at ASC, sp.updated_at DESC
        """
        params = ()

    if limit is not None:
        sql += "\nLIMIT %s"
        params = (*params, int(limit))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() or []
    finally:
        conn.close()

    targets: list[Target] = []
    for r in rows:
        sgid = str(r.get("story_generation_id") or "").strip()
        aid = str(r.get("assembly_id") or "").strip()
        if not sgid or not aid:
            continue
        if scope == "not-posted":
            reason = f"scheduled_posts status={r.get('status')}"
        elif scope == "all-rendered":
            reason = "assembly has rendered_slides"
        else:
            reason = "explicit story id"
        targets.append(Target(story_generation_id=sgid, assembly_id=aid, reason=reason))

    # De-dupe (some stories may have multiple scheduled_posts pointing at same assembly)
    dedup: dict[str, Target] = {}
    for t in targets:
        dedup[t.assembly_id] = t
    return list(dedup.values())


def _fetch_assembly(*, assembly_id: str) -> dict[str, Any] | None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text as id, story_generation_id::text as story_generation_id, assembly_data
                FROM story_assemblies
                WHERE id = %s::uuid
                LIMIT 1
                """,
                (assembly_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _upsert_rendered_slides(existing: list[dict] | None, updates: list[dict]) -> list[dict]:
    """
    Merge by `index` (preferred) and return a stable list sorted by index.
    """
    by_index: dict[int, dict] = {}
    for i, item in enumerate(existing or []):
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index", i))
        except Exception:
            idx = i
        by_index[idx] = dict(item)

    for item in updates:
        try:
            idx = int(item.get("index"))
        except Exception:
            continue
        by_index[idx] = dict(item)

    return [by_index[k] for k in sorted(by_index.keys())]


async def _process_target(
    *,
    target: Target,
    slides_mode: str,
    force_hydrate: bool,
    dry_run: bool,
    object_prefix: str,
    preview_dir: str | None,
    renderer: Renderer,
) -> dict[str, Any]:
    """
    slides_mode: "cover" | "all"
    """
    row = await asyncio.to_thread(_fetch_assembly, assembly_id=target.assembly_id)
    if not row:
        return {"assembly_id": target.assembly_id, "story_generation_id": target.story_generation_id, "status": "missing"}

    story_id = str(row.get("story_generation_id") or target.story_generation_id)
    assembly_id = str(row.get("id") or target.assembly_id)
    assembly_data = row.get("assembly_data") or {}

    # Hydrate from story DB rows so cover content/tag is current.
    story_data = await asyncio.to_thread(get_story_full_data, story_id)
    if story_data:
        hydrated, changed = hydrate_assembly_from_story(assembly_data, story_data, force=bool(force_hydrate))
        if changed and assembly_id and not dry_run:
            await asyncio.to_thread(update_assembly_data, assembly_id=assembly_id, assembly_data=hydrated)
            assembly_data = hydrated

    existing_rendered = None
    if isinstance(assembly_data, dict):
        existing_rendered = assembly_data.get("rendered_slides")
    if not isinstance(existing_rendered, list):
        existing_rendered = None

    # Decide selection
    slide_indices: set[int] | None
    if slides_mode == "cover":
        # Only render the first visible slide (index 0) BUT keep total slide count correct.
        # If there is no prior rendered_slides, we render all to avoid leaving the post incomplete.
        # If we forced hydration, we also render all to avoid page-number mismatches.
        slide_indices = {0} if (existing_rendered and not force_hydrate) else None
    else:
        slide_indices = None

    rendered = await render_assembly_to_png_bytes_selected(
        assembly_data,
        slide_indices=slide_indices,
        renderer=renderer,
    )
    if not rendered:
        return {
            "assembly_id": assembly_id,
            "story_generation_id": story_id,
            "status": "no_visible_slides",
        }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    object_base = f"{object_prefix.rstrip('/')}/{story_id}/{timestamp}"

    # Optional: write local previews (always safe; doesn't touch Supabase/DB)
    preview_paths: list[str] = []
    if preview_dir:
        base = os.path.abspath(preview_dir)
        story_preview_dir = os.path.join(base, story_id, timestamp)
        os.makedirs(story_preview_dir, exist_ok=True)
        for slide in rendered:
            p = os.path.join(story_preview_dir, slide.filename)
            await asyncio.to_thread(_write_bytes_file, p, slide.png_bytes)
            preview_paths.append(p)

    updates: list[dict] = []
    sample_paths: list[str] = []
    for idx, slide in enumerate(rendered):
        # Note: render_assembly_to_png_bytes_selected encodes the slide index into the filename
        # (e.g., "01_cover.png"); we also store index so later patching is easy.
        visible_index = None
        try:
            visible_index = int(slide.filename.split("_", 1)[0]) - 1
        except Exception:
            visible_index = idx

        object_path = f"{object_base}/{slide.filename}"
        if dry_run:
            url = f"(dry-run) {object_path}"
        else:
            url = await asyncio.to_thread(
                upload_bytes_to_supabase,
                data=slide.png_bytes,
                content_type="image/png",
                object_path=object_path,
            )
        if len(sample_paths) < 5:
            sample_paths.append(object_path)
        updates.append(
            {"index": int(visible_index), "filename": slide.filename, "public_url": url, "sha256": slide.sha256}
        )

    # Persist
    if dry_run:
        final_rendered_slides = _upsert_rendered_slides(existing_rendered, updates) if existing_rendered else updates
        return {
            "assembly_id": assembly_id,
            "story_generation_id": story_id,
            "status": "dry_run",
            "slides_updated": len(updates),
            "rendered_slides_len": len(final_rendered_slides),
            "sample_object_paths": sample_paths,
            "preview_paths": preview_paths,
        }

    final_rendered_slides = _upsert_rendered_slides(existing_rendered, updates) if existing_rendered else updates
    await asyncio.to_thread(save_rendered_slides, story_id, final_rendered_slides, assembly_id=assembly_id)

    return {
        "assembly_id": assembly_id,
        "story_generation_id": story_id,
        "status": "updated",
        "slides_updated": len(updates),
        "rendered_slides_len": len(final_rendered_slides),
        "sample_object_paths": sample_paths,
        "preview_paths": preview_paths,
    }


async def _amain() -> int:
    ap = argparse.ArgumentParser(description="Re-render + re-upload assembled slide images to Supabase.")
    ap.add_argument("--scope", choices=["all-rendered", "not-posted", "story"], default="not-posted")
    ap.add_argument("--slides", choices=["cover", "all"], default="cover", help="Render only the cover or all slides.")
    ap.add_argument("--story-id", default=None, help="Only used when --scope=story")
    ap.add_argument("--limit", type=int, default=None, help="Limit number of targets (debug/safety).")
    ap.add_argument("--concurrency", type=int, default=2, help="Concurrent renders (Playwright).")
    ap.add_argument(
        "--force-hydrate",
        action="store_true",
        help="Force re-hydrating assembly content from story tables (may overwrite some manual edits).",
    )
    ap.add_argument(
        "--object-prefix",
        default="story-posts",
        help="Supabase object prefix inside the bucket (default: story-posts).",
    )
    ap.add_argument(
        "--preview-dir",
        default=None,
        help="Optional local directory to write rendered PNG previews (safe for dry-run verification).",
    )
    ap.add_argument("--dry-run", action="store_true", help="Select + render but do NOT upload or update DB.")
    args = ap.parse_args()

    targets = _select_targets(scope=args.scope, limit=args.limit, story_id=args.story_id)
    if not targets:
        print("No targets found.")
        return 0

    print(f"Targets: {len(targets)} (scope={args.scope}, slides={args.slides}, dry_run={args.dry_run})")
    for t in targets[: min(10, len(targets))]:
        print(f" - story={t.story_generation_id} assembly={t.assembly_id} ({t.reason})")
    if len(targets) > 10:
        print(" - ...")

    sem = asyncio.Semaphore(max(1, int(args.concurrency)))

    async with Renderer() as renderer:
        async def _guarded(t: Target) -> dict[str, Any]:
            async with sem:
                return await _process_target(
                    target=t,
                    slides_mode=args.slides,
                    force_hydrate=bool(args.force_hydrate),
                    dry_run=bool(args.dry_run),
                    object_prefix=args.object_prefix,
                    preview_dir=args.preview_dir,
                    renderer=renderer,
                )

        results = await asyncio.gather(*[_guarded(t) for t in targets], return_exceptions=False)

    updated = [r for r in results if r.get("status") == "updated"]
    dry = [r for r in results if r.get("status") == "dry_run"]
    missing = [r for r in results if r.get("status") == "missing"]
    no_slides = [r for r in results if r.get("status") == "no_visible_slides"]

    print("")
    print("Details (first 10):")
    for r in results[: min(10, len(results))]:
        print(
            f" - story={r.get('story_generation_id')} assembly={r.get('assembly_id')} "
            f"status={r.get('status')} slides_updated={r.get('slides_updated')} rendered_slides_len={r.get('rendered_slides_len')}"
        )
        sample = r.get("sample_object_paths") or []
        if isinstance(sample, list) and sample:
            for p in sample[:3]:
                print(f"    - would_write: {p}")
        previews = r.get("preview_paths") or []
        if isinstance(previews, list) and previews:
            for p in previews[:3]:
                print(f"    - preview_png: {p}")

    print("")
    print("Summary:")
    print(f" - updated: {len(updated)}")
    print(f" - dry_run: {len(dry)}")
    print(f" - missing: {len(missing)}")
    print(f" - no_visible_slides: {len(no_slides)}")
    print(f" - finished_at: {_iso_utc()}")
    return 0


def _write_bytes_file(path: str, data: bytes) -> None:
    # Helper for asyncio.to_thread (kept at module scope for picklability).
    with open(path, "wb") as f:
        f.write(data)


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())


