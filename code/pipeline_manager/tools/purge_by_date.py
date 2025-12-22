"""
Purge pipeline-generated content by calendar date.

Default behavior is a dry-run that prints counts. Use --execute to actually delete.

This script is designed to clean up data created during failed/experimental runs so
you can re-run the pipeline without being affected by dedupe artifacts.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Any

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from pathlib import Path


def _parse_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit(f"Invalid --date '{s}'. Use YYYY-MM-DD.")


def _get_conn():
    # Load .env from repo root (same behavior as the apps)
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("POSTGRES_DB", "")
    user = os.getenv("POSTGRES_USER", "")
    password = os.getenv("POSTGRES_PASSWORD", "")

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
    )


@dataclass
class Preview:
    target_date: str
    run_ids: int
    story_generation_ids: int
    leads: int
    story_research: int
    story_generations: int
    story_slides: int
    story_photos: int
    story_thumbnails: int
    pipeline_story_status: int
    pipeline_runs: int
    story_assemblies: int
    scheduled_posts: int
    processed_urls: int
    story_memory: int


PREVIEW_SQL = """
WITH
  runs AS (
    SELECT id FROM pipeline_runs WHERE created_at::date = %(d)s
  ),
  gens AS (
    SELECT id FROM story_generations WHERE pipeline_run_id IN (SELECT id FROM runs)
  )
SELECT
  (SELECT COUNT(*) FROM runs) AS run_ids,
  (SELECT COUNT(*) FROM gens) AS story_generation_ids,
  (SELECT COUNT(*) FROM leads WHERE pipeline_run_id IN (SELECT id FROM runs)) AS leads,
  (SELECT COUNT(*) FROM story_research WHERE pipeline_run_id IN (SELECT id FROM runs)) AS story_research,
  (SELECT COUNT(*) FROM story_generations WHERE pipeline_run_id IN (SELECT id FROM runs)) AS story_generations,
  (SELECT COUNT(*) FROM story_slides WHERE story_generation_id IN (SELECT id FROM gens)) AS story_slides,
  (SELECT COUNT(*) FROM story_photos WHERE pipeline_run_id IN (SELECT id FROM runs)) AS story_photos,
  (SELECT COUNT(*) FROM story_thumbnails WHERE pipeline_run_id IN (SELECT id FROM runs)) AS story_thumbnails,
  (SELECT COUNT(*) FROM pipeline_story_status WHERE pipeline_run_id IN (SELECT id FROM runs)) AS pipeline_story_status,
  (SELECT COUNT(*) FROM pipeline_runs WHERE id IN (SELECT id FROM runs)) AS pipeline_runs,
  (SELECT COUNT(*) FROM story_assemblies WHERE story_generation_id IN (SELECT id FROM gens)) AS story_assemblies,
  (SELECT COUNT(*) FROM scheduled_posts WHERE story_generation_id IN (SELECT id FROM gens)) AS scheduled_posts,
  (SELECT COUNT(*) FROM processed_urls WHERE processed_at::date = %(d)s) AS processed_urls,
  (SELECT COUNT(*) FROM story_memory WHERE created_at::date = %(d)s) AS story_memory
;
"""


EXECUTE_STMTS = [
    # Create temp tables for this transaction to hold IDs.
    (
        """
        CREATE TEMP TABLE _purge_runs (id uuid PRIMARY KEY) ON COMMIT DROP;
        INSERT INTO _purge_runs (id)
        SELECT id FROM pipeline_runs WHERE created_at::date = %(d)s;
        """,
        True,
    ),
    (
        """
        CREATE TEMP TABLE _purge_gens (id uuid PRIMARY KEY) ON COMMIT DROP;
        INSERT INTO _purge_gens (id)
        SELECT id FROM story_generations WHERE pipeline_run_id IN (SELECT id FROM _purge_runs);
        """,
        True,
    ),
    # Scheduled posts (FK -> story_generations)
    ("DELETE FROM scheduled_posts WHERE story_generation_id IN (SELECT id FROM _purge_gens);", False),
    # Assemblies (FK -> story_generations)
    ("DELETE FROM story_assemblies WHERE story_generation_id IN (SELECT id FROM _purge_gens);", False),
    # Slides (FK -> story_generations)
    ("DELETE FROM story_slides WHERE story_generation_id IN (SELECT id FROM _purge_gens);", False),
    # Pipeline-tagged tables
    ("DELETE FROM story_thumbnails WHERE pipeline_run_id IN (SELECT id FROM _purge_runs);", False),
    ("DELETE FROM story_photos WHERE pipeline_run_id IN (SELECT id FROM _purge_runs);", False),
    ("DELETE FROM story_generations WHERE pipeline_run_id IN (SELECT id FROM _purge_runs);", False),
    ("DELETE FROM story_research WHERE pipeline_run_id IN (SELECT id FROM _purge_runs);", False),
    ("DELETE FROM leads WHERE pipeline_run_id IN (SELECT id FROM _purge_runs);", False),
    ("DELETE FROM pipeline_story_status WHERE pipeline_run_id IN (SELECT id FROM _purge_runs);", False),
    # Finally, runs themselves
    ("DELETE FROM pipeline_runs WHERE id IN (SELECT id FROM _purge_runs);", False),
    # Dedupe artifacts created today (global, not run-scoped)
    ("DELETE FROM processed_urls WHERE processed_at::date = %(d)s;", False),
    ("DELETE FROM story_memory WHERE created_at::date = %(d)s;", False),
]


def _fetch_one(cur, sql: str, params: Dict[str, Any]) -> Dict[str, Any]:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Purge pipeline-generated content by date (dry-run by default).")
    ap.add_argument("--date", required=True, help="Calendar date in YYYY-MM-DD (e.g. 2025-12-21)")
    ap.add_argument("--execute", action="store_true", help="Actually delete. If omitted, only prints counts.")
    args = ap.parse_args()

    d = _parse_date(args.date)
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            counts = _fetch_one(cur, PREVIEW_SQL, {"d": d})
            preview = Preview(
                target_date=str(d),
                run_ids=int(counts.get("run_ids", 0) or 0),
                story_generation_ids=int(counts.get("story_generation_ids", 0) or 0),
                leads=int(counts.get("leads", 0) or 0),
                story_research=int(counts.get("story_research", 0) or 0),
                story_generations=int(counts.get("story_generations", 0) or 0),
                story_slides=int(counts.get("story_slides", 0) or 0),
                story_photos=int(counts.get("story_photos", 0) or 0),
                story_thumbnails=int(counts.get("story_thumbnails", 0) or 0),
                pipeline_story_status=int(counts.get("pipeline_story_status", 0) or 0),
                pipeline_runs=int(counts.get("pipeline_runs", 0) or 0),
                story_assemblies=int(counts.get("story_assemblies", 0) or 0),
                scheduled_posts=int(counts.get("scheduled_posts", 0) or 0),
                processed_urls=int(counts.get("processed_urls", 0) or 0),
                story_memory=int(counts.get("story_memory", 0) or 0),
            )

            print(f"=== Purge Preview for {preview.target_date} ===")
            print(f"pipeline_runs:           {preview.pipeline_runs} (run_ids={preview.run_ids})")
            print(f"pipeline_story_status:   {preview.pipeline_story_status}")
            print(f"leads (pipeline_run_id): {preview.leads}")
            print(f"story_research:          {preview.story_research}")
            print(f"story_generations:       {preview.story_generations} (gen_ids={preview.story_generation_ids})")
            print(f"story_slides:            {preview.story_slides}")
            print(f"story_photos:            {preview.story_photos}")
            print(f"story_thumbnails:        {preview.story_thumbnails}")
            print(f"story_assemblies*:       {preview.story_assemblies}")
            print(f"scheduled_posts*:        {preview.scheduled_posts}")
            print(f"processed_urls (date):   {preview.processed_urls}")
            print(f"story_memory (date):     {preview.story_memory}")
            print("")
            print("* story_assemblies / scheduled_posts are deleted only if they reference story_generations from runs on that date.")

            if not args.execute:
                print("\nDry-run only. Re-run with --execute to delete.")
                return 0

            if preview.pipeline_runs == 0 and preview.processed_urls == 0 and preview.story_memory == 0:
                print("Nothing to delete for that date.")
                return 0

            # Execute deletion transaction (CTEs don't span multiple statements, so we use temp tables)
            # The preview SELECTs may have opened a transaction; clear it first.
            try:
                conn.rollback()
            except Exception:
                pass

            cur.execute("BEGIN;")
            try:
                for sql, allow_multi in EXECUTE_STMTS:
                    # Some statements include multiple commands; psycopg2 allows this for simple cases.
                    cur.execute(sql, {"d": d})
                cur.execute("COMMIT;")
            except Exception:
                cur.execute("ROLLBACK;")
                raise

            print("✅ Purge completed.")
            return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())


