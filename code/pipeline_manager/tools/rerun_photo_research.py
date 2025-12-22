"""
Re-run Photo Research for a pipeline run (overwrite existing photo research).

Default behavior:
- Picks the most recent pipeline_runs row (by created_at)
- Deletes all story_photos for that run's stories (scoped to the run)
- Runs the pipeline_manager PhotoResearcherWorker for the same run_id

WARNING:
- This will make external API calls (Google Custom Search + OpenAI) and may incur cost.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv


def _get_conn():
    # Load .env from repo root (same behavior as the apps/tools)
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

    host = os.getenv("POSTGRES_HOST", "")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("POSTGRES_DB", "")
    user = os.getenv("POSTGRES_USER", "")
    password = os.getenv("POSTGRES_PASSWORD", "")
    connect_timeout = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))
    statement_timeout_ms = int(os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS", "120000"))

    if not (host and port and dbname and user):
        raise SystemExit(
            "Missing DB env vars. Need POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD."
        )

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        connect_timeout=connect_timeout,
        options=f"-c statement_timeout={statement_timeout_ms}",
    )


def _latest_run_id(conn) -> Optional[str]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id FROM pipeline_runs ORDER BY created_at DESC LIMIT 1;")
        row = cur.fetchone()
        return str(row["id"]) if row and row.get("id") else None


def _count_photos_for_run(conn, run_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM story_photos WHERE pipeline_run_id = %s;", (run_id,))
        return int(cur.fetchone()[0] or 0)


def _delete_photos_for_run(conn, run_id: str) -> int:
    """
    Delete story_photos scoped to this pipeline run.

    Also deletes any story_photos rows that match the run's story_research set
    but were not tagged with pipeline_run_id (defensive).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH sr_ids AS (
              SELECT id
              FROM story_research
              WHERE pipeline_run_id = %s
            )
            DELETE FROM story_photos sp
            WHERE sp.pipeline_run_id = %s
               OR sp.story_research_id IN (SELECT id FROM sr_ids);
            """,
            (run_id, run_id),
        )
        return int(cur.rowcount or 0)


def _tag_photo_with_run(photo_db, *, photo_id: str, run_id: str) -> None:
    # Use the same psycopg2 connection as the photo module so we avoid any other DB wrappers/timeouts.
    with photo_db.conn.cursor() as cur:
        cur.execute(
            "UPDATE story_photos SET pipeline_run_id = %s WHERE id = %s",
            (run_id, photo_id),
        )


def _process_story_photos(*, story: dict, run_id: str, photo_db) -> tuple[int, int]:
    """
    Process one story end-to-end using the photo_researcher module logic.
    Returns (photos_found, photos_approved).
    """
    from photo_researcher.generator import QueryGenerator
    from photo_researcher.searcher import ImageSearcher
    from photo_researcher.validator import Validator
    from photo_researcher.analyzer import VisualAnalyzer
    from photo_researcher.scraper import PageScraper
    from photo_researcher.placer import PhotoPlacer

    generator = QueryGenerator()
    searcher = ImageSearcher()
    validator = Validator()
    analyzer = VisualAnalyzer()
    scraper = PageScraper()
    placer = PhotoPlacer()

    # Normalize for photo_researcher expectations
    if not story.get("title"):
        story["title"] = story.get("lead_title") or story.get("hook_title") or "Untitled"

    queries = generator.generate_queries(story)

    valid_candidates: list[dict] = []
    seen_urls: set[str] = set()
    for query in queries:
        results = searcher.search(query, num_results=5)
        for res in results:
            url = (res or {}).get("image_url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            if validator.check_url(url):
                res["search_query"] = query
                valid_candidates.append(res)

    ground_truth = ""
    research_data = story.get("research_data") or {}
    if isinstance(research_data, dict):
        ground_truth = research_data.get("ground_truth") or ""

    photos_found = 0
    photos_approved = 0
    story_research_id = str(story.get("story_research_id") or "")
    story_generation_id = str(story.get("id") or "")

    for candidate in valid_candidates:
        source_url = candidate.get("source_page_url")
        source_context = scraper.scrape_context(source_url) if source_url else {}
        analysis = analyzer.analyze(candidate["image_url"], ground_truth, source_context)
        candidate.update(analysis)

        candidate.setdefault("metadata", {})
        candidate["metadata"]["source_context"] = {
            "title": source_context.get("page_title"),
            "description": source_context.get("page_description"),
        }

        photo_id = str(photo_db.save_photo_candidate(story_research_id, candidate))
        _tag_photo_with_run(photo_db, photo_id=photo_id, run_id=run_id)

        photos_found += 1
        if candidate.get("status") == "approved":
            photos_approved += 1

    # Placement (best-effort)
    try:
        approved = photo_db.fetch_approved_photos(story_research_id)
        slides = story.get("slides") or []
        story_title = str(story.get("hook_title") or story.get("title") or "")
        if approved and slides:
            placement = placer.place_photos(
                story_title=story_title,
                slides=list(slides),
                photos=[dict(p) for p in approved],
            )
            if placement and isinstance(placement, dict):
                photo_db.apply_photo_placements(
                    story_generation_id=story_generation_id,
                    placements=placement.get("placements") or [],
                )
    except Exception as e:
        print(f"[warn] placement failed for {story.get('title')}: {e}")

    return photos_found, photos_approved


async def _run_photo_research_direct(run_id: str, *, limit: Optional[int] = None) -> dict:
    # Ensure repo root is on sys.path so `import pipeline_manager` works when this script
    # is executed as a file (python pipeline_manager/tools/rerun_photo_research.py).
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    print("Loading generations for run...", flush=True)
    from pipeline_manager.db import get_generations_for_run
    from photo_researcher.db import Database as PhotoDB

    gens = get_generations_for_run(run_id)
    print(f"Loaded {len(gens) if gens else 0} generations.", flush=True)
    if limit is not None:
        gens = gens[: max(0, int(limit))]
        print(f"Applying limit={limit} => {len(gens)} generations.", flush=True)

    if not gens:
        return {"success": True, "photos_found": 0, "photos_approved": 0, "completed": 0}

    print("Opening photo_researcher DB connection...", flush=True)
    photo_db = PhotoDB()
    print("Photo DB ready.", flush=True)
    try:
        photos_found = 0
        photos_approved = 0
        completed = 0
        errors: list[dict] = []

        for idx, g in enumerate(gens, start=1):
            title = g.get("lead_title") or g.get("hook_title") or str(g.get("id") or "")
            print(f"[{idx}/{len(gens)}] {title}")
            try:
                found, approved = await asyncio.to_thread(
                    _process_story_photos, story=dict(g), run_id=run_id, photo_db=photo_db
                )
                photos_found += found
                photos_approved += approved
                completed += 1
            except Exception as e:
                errors.append({"story_generation_id": str(g.get("id") or ""), "title": str(title), "error": str(e)})
                print(f"[error] failed story: {title}: {e}")

        return {
            "success": len(errors) == 0,
            "photos_found": photos_found,
            "photos_approved": photos_approved,
            "completed": completed,
            "errors": errors,
        }
    finally:
        photo_db.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-run Photo Research for a pipeline run (overwrite existing).")
    ap.add_argument("--run-id", help="Pipeline run UUID. If omitted, uses most recent run.")
    ap.add_argument("--limit", type=int, default=None, help="Process only first N stories (for testing).")
    ap.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete + rerun. If omitted, prints what would happen.",
    )
    args = ap.parse_args()

    print("Connecting to DB...", flush=True)
    conn = _get_conn()
    try:
        run_id = (args.run_id or "").strip() or _latest_run_id(conn)
        if not run_id:
            raise SystemExit("No pipeline_runs found, and no --run-id provided.")

        before = _count_photos_for_run(conn, run_id)
        print(f"Run: {run_id}")
        print(f"Existing story_photos tagged to this run: {before}")

        if not args.execute:
            print("\nDry-run only. Re-run with --execute to delete + rerun photo research.")
            return 0

        print("\nDeleting existing photo research rows...")
        deleted = _delete_photos_for_run(conn, run_id)
        conn.commit()
        after_delete = _count_photos_for_run(conn, run_id)
        print(f"Deleted story_photos rows: {deleted}")
        print(f"Remaining story_photos tagged to this run: {after_delete}")

        print("\nRe-running photo research...")
        result = asyncio.run(_run_photo_research_direct(run_id, limit=args.limit))
        print("\nDone.")
        print(result)

        after_rerun = _count_photos_for_run(conn, run_id)
        print(f"\nFinal story_photos tagged to this run: {after_rerun}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())


