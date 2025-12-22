"""
Read-only DB audit: show how much data was created/updated on a given day.

Usage (from repo root):
  python ops/db_audit_day.py --date 2025-12-21

Connection:
  - Prefer DATABASE_URL from env
  - Else build from POSTGRES_* env vars

This script is intended to help validate cancellation/deletion logic by checking
what rows exist for a day.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable


def _load_dotenv_best_effort() -> None:
    # Match other modules: allow repo root .env and process env.
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    load_dotenv(os.path.join(repo_root, ".env"))
    load_dotenv()


_load_dotenv_best_effort()


def _build_dsn() -> str:
    dsn = (os.getenv("DATABASE_URL") or "").strip()
    if dsn:
        return dsn
    host = (os.getenv("POSTGRES_HOST") or "").strip()
    port = (os.getenv("POSTGRES_PORT") or "5432").strip()
    db = (os.getenv("POSTGRES_DB") or "").strip()
    user = (os.getenv("POSTGRES_USER") or "").strip()
    pw = (os.getenv("POSTGRES_PASSWORD") or "").strip()
    if not all([host, port, db, user]):
        raise SystemExit(
            "Missing DB connection info. Set DATABASE_URL or POSTGRES_HOST/POSTGRES_PORT/POSTGRES_DB/POSTGRES_USER/POSTGRES_PASSWORD."
        )
    # password may be empty in some local configs
    auth = f"{user}:{pw}" if pw else user
    return f"postgresql://{auth}@{host}:{port}/{db}"


def _connect():
    # Prefer psycopg2 (used throughout repo), fall back to psycopg if available.
    try:
        import psycopg2  # type: ignore
        import psycopg2.extras  # type: ignore

        conn = psycopg2.connect(_build_dsn(), cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = True
        return conn
    except Exception:
        try:
            import psycopg  # type: ignore

            conn = psycopg.connect(_build_dsn(), row_factory=psycopg.rows.dict_row)
            conn.autocommit = True
            return conn
        except Exception as e:
            raise SystemExit(f"Failed to import/connect with psycopg2/psycopg: {e}")


@dataclass(frozen=True)
class TableAudit:
    label: str
    table: str
    created_col: str = "created_at"
    updated_col: str | None = "updated_at"
    extra_where: str | None = None


DEFAULT_TABLES: list[TableAudit] = [
    # Has updated_at
    TableAudit("pipeline_runs", "pipeline_runs", updated_col="updated_at"),
    TableAudit("pipeline_story_status", "pipeline_story_status", updated_col="updated_at"),
    TableAudit("story_assemblies", "story_assemblies", updated_col="updated_at"),
    TableAudit("scheduled_posts", "scheduled_posts", updated_col="updated_at"),
    TableAudit("ig_access_tokens", "ig_access_tokens", updated_col="updated_at"),

    # No updated_at in schema (created-only, or other timestamps exist)
    TableAudit("leads", "leads", updated_col=None),
    TableAudit("story_research", "story_research", updated_col=None),
    TableAudit("story_generations", "story_generations", updated_col=None),
    TableAudit("story_slides", "story_slides", updated_col=None),
    TableAudit("story_photos", "story_photos", updated_col=None),
    TableAudit("story_thumbnails", "story_thumbnails", updated_col=None),
    TableAudit("schedule_approvals", "schedule_approvals", updated_col=None),
    TableAudit("discovery_topics", "discovery_topics", updated_col=None),
    TableAudit("processed_urls", "processed_urls", created_col="processed_at", updated_col=None),
]


def _utc_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _fmt_ts(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc).isoformat()
        return v.astimezone(timezone.utc).isoformat()
    return str(v)


def _rows_to_table(rows: Iterable[dict]) -> str:
    rows = list(rows)
    if not rows:
        return "(no rows)"
    # Compute simple column widths
    cols = list(rows[0].keys())
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    lines = []
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    lines.append(header)
    lines.append(sep)
    for r in rows:
        lines.append(" | ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))
    return "\n".join(lines)


def audit_day(*, d: date) -> int:
    start, end = _utc_bounds(d)
    conn = _connect()
    try:
        cur = conn.cursor()
        print(f"DB audit (UTC day): {d.isoformat()}  [{start.isoformat()} .. {end.isoformat()})")
        print(f"DSN: {_build_dsn().split('@')[-1]}")  # avoid printing creds
        print("")

        for t in DEFAULT_TABLES:
            where = f"{t.created_col} >= %s AND {t.created_col} < %s"
            if t.extra_where:
                where = f"({where}) AND ({t.extra_where})"

            sql = f"""
                SELECT
                  %s::text AS table,
                  COUNT(*)::bigint AS created_count,
                  MIN({t.created_col}) AS created_min,
                  MAX({t.created_col}) AS created_max
                FROM {t.table}
                WHERE {where}
            """
            cur.execute(sql, (t.label, start, end))
            row = cur.fetchone() or {}

            created_count = int(row.get("created_count") or 0)
            created_min = row.get("created_min")
            created_max = row.get("created_max")

            updated_count = None
            updated_min = None
            updated_max = None
            if t.updated_col:
                sql_u = f"""
                    SELECT
                      COUNT(*)::bigint AS updated_count,
                      MIN({t.updated_col}) AS updated_min,
                      MAX({t.updated_col}) AS updated_max
                    FROM {t.table}
                    WHERE {t.updated_col} >= %s AND {t.updated_col} < %s
                """
                cur.execute(sql_u, (start, end))
                row_u = cur.fetchone() or {}
                updated_count = int(row_u.get("updated_count") or 0)
                updated_min = row_u.get("updated_min")
                updated_max = row_u.get("updated_max")

            print(
                f"- {t.label}: created={created_count}"
                + (f" (min={_fmt_ts(created_min)} max={_fmt_ts(created_max)})" if created_count else "")
                + (f" | updated={updated_count}" if updated_count is not None else "")
                + (f" (min={_fmt_ts(updated_min)} max={_fmt_ts(updated_max)})" if updated_count else "")
            )

        print("")

        # Drill-in: pipeline runs (if any) to validate cancellation/deletion behavior.
        cur.execute(
            """
            SELECT
              id::text AS pipeline_run_id,
              mode,
              status,
              created_at,
              started_at,
              completed_at,
              current_phase,
              error_message
            FROM pipeline_runs
            WHERE created_at >= %s AND created_at < %s
            ORDER BY created_at DESC
            LIMIT 25
            """,
            (start, end),
        )
        runs = cur.fetchall() or []
        print("Recent pipeline_runs created that day (up to 25):")
        print(_rows_to_table(runs))
        print("")

        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only DB audit for a given UTC day.")
    p.add_argument("--date", required=True, help="YYYY-MM-DD (interpreted as UTC day bounds)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        d = date.fromisoformat(str(args.date).strip())
    except Exception:
        raise SystemExit("Invalid --date. Use YYYY-MM-DD, e.g. --date 2025-12-21")
    return audit_day(d=d)


if __name__ == "__main__":
    raise SystemExit(main())


