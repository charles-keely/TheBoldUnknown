import argparse
import json
import logging
import os
from datetime import datetime, timezone

from scheduler.config import config
from scheduler.db import pick_one_assembly
from scheduler.instagram import (
    create_carousel_container,
    create_carousel_item,
    publish_media,
    wait_container_ready,
)
from scheduler.render import render_assembly_to_png_bytes_sync
from scheduler.storage import upload_bytes_to_supabase


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("scheduler")


def _compose_caption(caption: str | None, hashtags) -> str:
    cap = (caption or "").strip()
    tags = []
    if isinstance(hashtags, list):
        tags = [str(t).strip() for t in hashtags if str(t).strip()]
    elif isinstance(hashtags, str):
        tags = [t.strip() for t in hashtags.split() if t.strip()]

    if tags:
        tags_txt = " ".join([t if t.startswith("#") else f"#{t}" for t in tags])
        return (cap + ("\n\n" if cap else "") + tags_txt).strip()
    return cap


def cmd_test_post(args: argparse.Namespace) -> int:
    prefer_finalized = args.pick in ("finalized_first", "finalized")
    row = pick_one_assembly(prefer_finalized=prefer_finalized)
    if not row:
        raise SystemExit("No assembly found to post (need at least one row in story_assemblies).")

    story_id = str(row["story_generation_id"])
    title = row.get("hook_title") or story_id
    logger.info(f"Picked story_generation_id={story_id} title={title!r} status={row.get('assembly_status')}")

    assembly_data = row.get("assembly_data") or {}
    rendered = render_assembly_to_png_bytes_sync(assembly_data)
    if not rendered:
        raise SystemExit("Assembly had no visible slides to render.")

    logger.info(f"Rendered {len(rendered)} slides in-memory (no DB writes).")

    # Instagram carousel constraints: 2..10 items for CAROUSEL publishing.
    # For local-only rendering, allow 1..10 so we can test single-slide renders.
    max_items = int(args.max_items)
    if args.storage_mode == "local_only":
        if max_items < 1 or max_items > 10:
            raise SystemExit("--max-items must be between 1 and 10 for --storage-mode=local_only.")
    else:
        if max_items < 2 or max_items > 10:
            raise SystemExit("--max-items must be between 2 and 10 (Instagram carousel constraint).")
    if len(rendered) > max_items:
        logger.warning(
            f"Rendered {len(rendered)} slides but Instagram supports at most {max_items} per carousel. "
            f"Truncating to first {max_items}."
        )
        rendered = rendered[:max_items]
    if args.storage_mode != "local_only" and len(rendered) < 2 and not args.dry_run_publish:
        raise SystemExit(f"Need at least 2 slides to publish a carousel (got {len(rendered)}).")

    # Upload slides so Instagram can fetch them.
    upload_prefix = args.object_prefix.rstrip("/") if args.object_prefix else "story-posts"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    object_base = f"{upload_prefix}/{story_id}/{timestamp}"

    public_urls: list[str] = []
    if args.storage_mode == "local_only":
        out_dir = os.path.abspath(args.local_output_dir or os.path.join("scheduler", "output", story_id, timestamp))
        os.makedirs(out_dir, exist_ok=True)
        for slide in rendered:
            out_path = os.path.join(out_dir, slide.filename)
            with open(out_path, "wb") as f:
                f.write(slide.png_bytes)
            logger.info(f"Wrote {slide.filename} -> {out_path}")
        logger.info("storage_mode=local_only: skipping uploads and Instagram calls.")
        return 0

    for slide in rendered:
        object_path = f"{object_base}/{slide.filename}"
        url = upload_bytes_to_supabase(data=slide.png_bytes, content_type="image/png", object_path=object_path)
        public_urls.append(url)
        logger.info(f"Uploaded {slide.filename} -> {url}")

    caption = _compose_caption(row.get("instagram_caption"), row.get("hashtags"))
    if args.caption_override is not None:
        caption = args.caption_override

    payload_preview = {
        "story_generation_id": story_id,
        "assembly_id": str(row.get("assembly_id")),
        "assembly_status": row.get("assembly_status"),
        "slides": [{"filename": s.filename, "sha256": s.sha256, "public_url": u} for s, u in zip(rendered, public_urls)],
        "caption": caption,
        "dry_run_publish": bool(args.dry_run_publish),
        "db_writes": "disabled (read-only connection + no UPDATEs executed)",
    }
    if args.write_preview_json:
        with open(args.write_preview_json, "w", encoding="utf-8") as f:
            json.dump(payload_preview, f, indent=2)
        logger.info(f"Wrote preview json: {args.write_preview_json}")

    if args.dry_run_publish:
        logger.info("Dry-run publish enabled: stopping before Instagram Graph API calls.")
        return 0

    if not config.IG_USER_ID:
        raise SystemExit("Missing IG_USER_ID (or INSTAGRAM_USER_ID) env var.")

    # Create carousel items
    children: list[str] = []
    for url in public_urls:
        cid = create_carousel_item(ig_user_id=config.IG_USER_ID, image_url=url)
        children.append(cid)
        wait_container_ready(container_id=cid)
        logger.info(f"Carousel item ready: {cid}")

    # Create carousel container
    carousel_id = create_carousel_container(ig_user_id=config.IG_USER_ID, children=children, caption=caption)
    wait_container_ready(container_id=carousel_id)
    logger.info(f"Carousel container ready: {carousel_id}")

    # Publish
    media_id = publish_media(ig_user_id=config.IG_USER_ID, creation_id=carousel_id)
    logger.info(f"Published Instagram media id: {media_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scheduler", description="Publisher runner (no DB writes).")
    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("test-post", help="Render + upload + (optionally) publish one assembled story.")
    t.add_argument(
        "--pick",
        default=config.DEFAULT_PICK_STRATEGY,
        choices=("finalized_first", "finalized", "latest_any"),
        help="Which story to pick from DB.",
    )
    t.add_argument(
        "--dry-run-publish",
        action="store_true",
        help="Do everything except call Instagram Graph API publish endpoints.",
    )
    t.add_argument(
        "--object-prefix",
        default="story-posts",
        help="Supabase Storage path prefix (within bucket).",
    )
    t.add_argument(
        "--storage-mode",
        default="supabase",
        choices=("supabase", "local_only"),
        help="Where to place rendered PNGs. 'supabase' is required for real Instagram posting.",
    )
    t.add_argument(
        "--local-output-dir",
        default=None,
        help="When --storage-mode=local_only, write PNGs under this directory.",
    )
    t.add_argument(
        "--caption-override",
        default=None,
        help="If set, use this caption instead of DB instagram_caption/hashtags.",
    )
    t.add_argument(
        "--max-items",
        default="10",
        help="Max slides to publish in the carousel (Instagram supports 2..10). Default: 10.",
    )
    t.add_argument(
        "--write-preview-json",
        default=None,
        help="Optional path to write a json preview payload.",
    )
    t.set_defaults(func=cmd_test_post)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())


