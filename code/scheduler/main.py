import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone

from scheduler.config import config
from scheduler.db import pick_assemblies, pick_one_assembly
from scheduler.instagram import (
    create_carousel_container,
    create_carousel_item,
    publish_media,
    validate_ig_user_access,
    wait_container_ready,
)
from scheduler.render import render_assembly_to_png_bytes_sync
from scheduler.storage import upload_bytes_to_supabase
from scheduler.token_refresh import compute_expires_at, exchange_for_long_lived_token
from scheduler.token_store import TokenRecord, get_access_token_from_env, load_token_record, save_token_record
from scheduler.token_refresh import TokenRefreshError


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("scheduler")

def _token_expires_soon(*, expires_at: int | None, window_days: int, now: int | None = None) -> bool:
    if expires_at is None:
        return False
    now = int(now or time.time())
    return (int(expires_at) - now) <= max(0, int(window_days)) * 86400


def ensure_fresh_ig_token(*, force: bool = False) -> None:
    """
    Best-effort: ensure we have a non-expired IG access token available.

    Behavior:
    - If an env token is set, we will *not* overwrite it (env always wins), but we may still
      refresh+persist to the token store for unattended runs.
    - If no env token is set, we rely on the token store (scheduler/ig_token.json by default).
    - If app credentials are present, we refresh only when the stored token is missing/near expiry
      (or force=True).
    """
    store_path = config.IG_TOKEN_STORE_PATH
    env_token = (get_access_token_from_env() or "").strip()

    existing = load_token_record(store_path)
    if existing and existing.is_expired() and not config.META_APP_ID:
        # Can't refresh without app creds; fail with a clear message.
        raise SystemExit("Stored IG token is expired and META_APP_ID/META_APP_SECRET are not set to refresh it.")

    # If we don't have app creds, we can't auto-refresh; just ensure a token exists.
    if not config.META_APP_ID or not config.META_APP_SECRET:
        return

    window_days = int(config.TOKEN_REFRESH_WINDOW_DAYS)
    now = int(time.time())

    # Decide what token to exchange with:
    # - Prefer env token (user may have pasted a fresh one)
    # - Else existing store token
    exchange_token = env_token or (existing.access_token if existing else "")
    if not exchange_token:
        # Nothing to do; caller will error later when trying to use the token.
        return

    need_refresh = force
    if not existing:
        need_refresh = True
    elif existing.expires_at is not None and _token_expires_soon(expires_at=existing.expires_at, window_days=window_days, now=now):
        need_refresh = True

    if not need_refresh:
        return

    resp = exchange_for_long_lived_token(
        graph_api_version=config.GRAPH_API_VERSION,
        app_id=config.META_APP_ID,
        app_secret=config.META_APP_SECRET,
        fb_exchange_token=exchange_token,
    )
    new_token = resp.get("access_token")
    expires_in = resp.get("expires_in")
    token_type = resp.get("token_type")
    if not new_token:
        raise SystemExit(f"Token exchange returned no access_token: {resp}")

    expires_at = compute_expires_at(expires_in=expires_in, now=now)
    rec = TokenRecord(
        access_token=str(new_token),
        token_type=str(token_type) if token_type is not None else None,
        obtained_at=now,
        expires_in=int(expires_in) if expires_in is not None else None,
        expires_at=int(expires_at) if expires_at is not None else None,
        graph_api_version=config.GRAPH_API_VERSION,
        source="auto_refresh_preflight",
    )
    save_token_record(store_path, rec)
    logger.info(f"Auto-refreshed IG token into {store_path} (expires_at={_fmt_ts(rec.expires_at)}).")


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
    row = pick_one_assembly(prefer_finalized=prefer_finalized, approved_only=bool(args.approved_only))
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

    # Fail fast on Instagram auth before we upload anything.
    if not args.dry_run_publish and args.storage_mode != "local_only":
        if not config.IG_USER_ID:
            raise SystemExit("Missing IG_USER_ID (or INSTAGRAM_USER_ID) env var.")
        ensure_fresh_ig_token()
        validate_ig_user_access(ig_user_id=config.IG_USER_ID)

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


def _resolve_preview_path(pattern: str | None, *, story_id: str, index: int) -> str | None:
    if not pattern:
        return None
    return (
        pattern.replace("{story_id}", story_id)
        .replace("{index}", str(index))
    )


def _run_one_post_with_row(args: argparse.Namespace, row: dict, *, index: int) -> int:
    """
    Run the same flow as `test-post` but using a pre-selected DB row.
    """
    story_id = str(row["story_generation_id"])
    title = row.get("hook_title") or story_id
    logger.info(
        f"[{index}] Picked story_generation_id={story_id} title={title!r} status={row.get('assembly_status')} "
        f"approved_for_assembly={row.get('approved_for_assembly')}"
    )

    assembly_data = row.get("assembly_data") or {}
    rendered = render_assembly_to_png_bytes_sync(assembly_data)
    if not rendered:
        logger.warning(f"[{index}] Assembly had no visible slides to render; skipping.")
        return 2

    logger.info(f"[{index}] Rendered {len(rendered)} slides in-memory (no DB writes).")

    max_items = int(args.max_items)
    if args.storage_mode == "local_only":
        if max_items < 1 or max_items > 10:
            raise SystemExit("--max-items must be between 1 and 10 for --storage-mode=local_only.")
    else:
        if max_items < 2 or max_items > 10:
            raise SystemExit("--max-items must be between 2 and 10 (Instagram carousel constraint).")
    if len(rendered) > max_items:
        logger.warning(f"[{index}] Truncating {len(rendered)} slides to first {max_items}.")
        rendered = rendered[:max_items]
    if args.storage_mode != "local_only" and len(rendered) < 2 and not args.dry_run_publish:
        logger.warning(f"[{index}] Need at least 2 slides to publish a carousel (got {len(rendered)}); skipping.")
        return 2

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
            logger.info(f"[{index}] Wrote {slide.filename} -> {out_path}")
        logger.info(f"[{index}] storage_mode=local_only: skipping uploads and Instagram calls.")
        return 0

    for slide in rendered:
        object_path = f"{object_base}/{slide.filename}"
        url = upload_bytes_to_supabase(data=slide.png_bytes, content_type="image/png", object_path=object_path)
        public_urls.append(url)
        logger.info(f"[{index}] Uploaded {slide.filename} -> {url}")

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
    preview_path = _resolve_preview_path(args.write_preview_json, story_id=story_id, index=index)
    if preview_path:
        with open(preview_path, "w", encoding="utf-8") as f:
            json.dump(payload_preview, f, indent=2)
        logger.info(f"[{index}] Wrote preview json: {preview_path}")

    if args.dry_run_publish:
        logger.info(f"[{index}] Dry-run publish enabled: stopping before Instagram Graph API calls.")
        return 0

    # At this point, token preflight + validate_ig_user_access already happened in batch runner.
    children: list[str] = []
    for url in public_urls:
        cid = create_carousel_item(ig_user_id=config.IG_USER_ID, image_url=url)
        children.append(cid)
        wait_container_ready(container_id=cid)
        logger.info(f"[{index}] Carousel item ready: {cid}")

    carousel_id = create_carousel_container(ig_user_id=config.IG_USER_ID, children=children, caption=caption)
    wait_container_ready(container_id=carousel_id)
    logger.info(f"[{index}] Carousel container ready: {carousel_id}")

    media_id = publish_media(ig_user_id=config.IG_USER_ID, creation_id=carousel_id)
    logger.info(f"[{index}] Published Instagram media id: {media_id}")
    return 0


def cmd_test_post_batch(args: argparse.Namespace) -> int:
    """
    Publish multiple posts sequentially (useful for smoke testing).
    """
    count = int(args.count)
    if count <= 0:
        return 0

    prefer_finalized = args.pick in ("finalized_first", "finalized")
    approved_only = bool(args.approved_only)
    exclude_ids: list[str] = []
    if args.exclude_story_ids:
        raw = str(args.exclude_story_ids)
        exclude_ids = [s.strip() for s in raw.split(",") if s.strip()]

    # Fail fast once, before any uploads.
    if not args.dry_run_publish and args.storage_mode != "local_only":
        if not config.IG_USER_ID:
            raise SystemExit("Missing IG_USER_ID (or INSTAGRAM_USER_ID) env var.")
        ensure_fresh_ig_token()
        validate_ig_user_access(ig_user_id=config.IG_USER_ID)

    # Pull a few extra candidates in case some are not publishable (e.g., <2 slides).
    candidates = pick_assemblies(
        limit=max(count * 3, count),
        prefer_finalized=prefer_finalized,
        approved_only=approved_only,
        exclude_story_generation_ids=exclude_ids,
    )
    if not candidates:
        raise SystemExit("No assemblies found to post.")

    published = 0
    exit_code = 0
    sleep_s = float(args.sleep_seconds)

    for row in candidates:
        idx = published + 1
        rc = _run_one_post_with_row(args, row, index=idx)
        if rc == 0:
            published += 1
            if published >= count:
                break
            if sleep_s > 0:
                logger.info(f"Sleeping {sleep_s:.1f}s before next post...")
                time.sleep(sleep_s)
        else:
            exit_code = max(exit_code, rc)

    if published < count:
        raise SystemExit(f"Only published {published}/{count} posts (see logs).")
    return exit_code


def _fmt_ts(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


def cmd_refresh_token(args: argparse.Namespace) -> int:
    """
    Refresh / exchange the current IG access token into a long-lived token and persist it to a local token store.
    """
    if not config.META_APP_ID or not config.META_APP_SECRET:
        raise SystemExit("Missing META_APP_ID / META_APP_SECRET (required for token exchange).")

    store_path = args.token_store or config.IG_TOKEN_STORE_PATH
    now = int(time.time())

    existing = load_token_record(store_path)
    if existing and not args.force and existing.expires_at is not None:
        window_days = int(args.refresh_window_days or config.TOKEN_REFRESH_WINDOW_DAYS)
        window_s = max(0, window_days) * 86400
        # If token is still comfortably valid, avoid rotating it unnecessarily.
        if (existing.expires_at - now) > window_s:
            logger.info(
                "Token is still valid; no refresh needed "
                f"(expires_at={_fmt_ts(existing.expires_at)} window_days={window_days}). "
                "Use --force to refresh anyway."
            )
            return 0

    input_token = (args.input_token or "").strip() or (get_access_token_from_env() or "").strip()
    if not input_token and existing:
        input_token = existing.access_token
    if not input_token:
        raise SystemExit(
            "No input token found. Provide --input-token or set IG_ACCESS_TOKEN in env for the first exchange."
        )

    try:
        resp = exchange_for_long_lived_token(
            graph_api_version=config.GRAPH_API_VERSION,
            app_id=config.META_APP_ID,
            app_secret=config.META_APP_SECRET,
            fb_exchange_token=input_token,
        )
    except TokenRefreshError as e:
        msg = str(e)
        # Common case: expired seed token (Meta OAuth 190/463).
        if "code\":190" in msg and "error_subcode\":463" in msg:
            raise SystemExit(
                "Your current IG user access token is expired, so it cannot be exchanged/refreshed.\n"
                "Generate a fresh token (same permissions), update it in `.env` as IG_USER_ACCESS_TOKEN (or IG_ACCESS_TOKEN),\n"
                "then rerun: `python -m scheduler.main refresh-token --force`."
            ) from e
        raise SystemExit(f"Token refresh failed: {msg}") from e
    new_token = resp.get("access_token")
    expires_in = resp.get("expires_in")
    token_type = resp.get("token_type")
    if not new_token:
        raise SystemExit(f"Token exchange returned no access_token: {resp}")

    expires_at = compute_expires_at(expires_in=expires_in, now=now)
    rec = TokenRecord(
        access_token=str(new_token),
        token_type=str(token_type) if token_type is not None else None,
        obtained_at=now,
        expires_in=int(expires_in) if expires_in is not None else None,
        expires_at=int(expires_at) if expires_at is not None else None,
        graph_api_version=config.GRAPH_API_VERSION,
        source="fb_exchange_token",
    )
    save_token_record(store_path, rec)
    logger.info(f"Saved refreshed token to {store_path} (expires_at={_fmt_ts(rec.expires_at)}).")
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
        "--approved-only",
        action="store_true",
        help="Only pick stories marked approved_for_assembly=true in Pre-Assembler.",
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

    b = sub.add_parser("test-post-batch", help="Publish N posts sequentially (useful for testing).")
    b.add_argument("--count", default="2", help="How many posts to publish. Default: 2.")
    b.add_argument(
        "--pick",
        default=config.DEFAULT_PICK_STRATEGY,
        choices=("finalized_first", "finalized", "latest_any"),
        help="Which stories to pick from DB.",
    )
    b.add_argument(
        "--approved-only",
        action="store_true",
        help="Only pick stories marked approved_for_assembly=true in Pre-Assembler.",
    )
    b.add_argument(
        "--dry-run-publish",
        action="store_true",
        help="Do everything except call Instagram Graph API publish endpoints.",
    )
    b.add_argument(
        "--object-prefix",
        default="story-posts",
        help="Supabase Storage path prefix (within bucket).",
    )
    b.add_argument(
        "--storage-mode",
        default="supabase",
        choices=("supabase", "local_only"),
        help="Where to place rendered PNGs. 'supabase' is required for real Instagram posting.",
    )
    b.add_argument(
        "--local-output-dir",
        default=None,
        help="When --storage-mode=local_only, write PNGs under this directory.",
    )
    b.add_argument(
        "--caption-override",
        default=None,
        help="If set, use this caption instead of DB instagram_caption/hashtags.",
    )
    b.add_argument(
        "--max-items",
        default="10",
        help="Max slides to publish in the carousel (Instagram supports 2..10). Default: 10.",
    )
    b.add_argument(
        "--write-preview-json",
        default="scheduler/test_post_preview_batch_{index}_{story_id}.json",
        help="Path pattern for json preview payload. Supports {index} and {story_id}.",
    )
    b.add_argument(
        "--sleep-seconds",
        default="5",
        help="Seconds to sleep between posts. Default: 5.",
    )
    b.add_argument(
        "--exclude-story-ids",
        default=None,
        help="Comma-separated story_generation_id values to skip (useful for repeated test runs).",
    )
    b.set_defaults(func=cmd_test_post_batch)

    r = sub.add_parser("refresh-token", help="Exchange/refresh the IG access token and store it locally.")
    r.add_argument(
        "--input-token",
        default=None,
        help="Optional token to exchange. If omitted, uses IG_ACCESS_TOKEN env or the existing token store.",
    )
    r.add_argument(
        "--token-store",
        default=None,
        help="Path to write token JSON (default: SCHEDULER_IG_TOKEN_STORE or scheduler/ig_token.json).",
    )
    r.add_argument(
        "--refresh-window-days",
        default=None,
        help="Only refresh if token expires within this many days (default: SCHEDULER_TOKEN_REFRESH_WINDOW_DAYS).",
    )
    r.add_argument("--force", action="store_true", help="Refresh even if token is not near expiry.")
    r.set_defaults(func=cmd_refresh_token)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())


