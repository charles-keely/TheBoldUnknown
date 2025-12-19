import psycopg2
from psycopg2.extras import RealDictCursor
import json
from typing import List, Dict, Any, Optional
from .config import config

class Database:
    def __init__(self):
        self.conn = psycopg2.connect(config.DATABASE_URL)
        self._has_primary_sources_columns: Optional[bool] = None
        self._has_primary_source_urls_columns: Optional[bool] = None

    def _column_exists(self, *, table: str, column: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                  AND column_name = %s
                LIMIT 1
                """,
                (table, column),
            )
            return cur.fetchone() is not None

    @property
    def has_primary_sources_columns(self) -> bool:
        if self._has_primary_sources_columns is None:
            self._has_primary_sources_columns = self._column_exists(
                table="story_research", column="primary_sources"
            )
        return bool(self._has_primary_sources_columns)

    @property
    def has_primary_source_urls_columns(self) -> bool:
        if self._has_primary_source_urls_columns is None:
            self._has_primary_source_urls_columns = self._column_exists(
                table="story_research", column="primary_source_urls"
            )
        return bool(self._has_primary_source_urls_columns)

    def fetch_queued_stories(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        Fetches stories from story_research with status 'queued'.
        Joins with leads table to get context.
        """
        query = """
            SELECT 
                sr.id as research_id,
                sr.lead_id,
                sr.status,
                sr.notes as curator_notes,
                l.title,
                l.url,
                l.summary,
                l.brand_score,
                l.virality_score,
                l.viral_hook
            FROM story_research sr
            JOIN leads l ON sr.lead_id = l.id
            WHERE sr.status = 'queued'
            ORDER BY sr.priority DESC NULLS LAST, sr.created_at ASC
        """
        if limit:
            query += f" LIMIT {limit}"
            
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query)
            return cur.fetchall()

    def update_research_results(self, research_id: str, research_data: Dict, status: str = 'completed'):
        """
        Updates the research_data and status for a story.
        """
        primary_sources = research_data.get("primary_sources") if isinstance(research_data, dict) else None
        primary_source_urls = research_data.get("primary_source_urls") if isinstance(research_data, dict) else None

        with self.conn.cursor() as cur:
            if self.has_primary_sources_columns and self.has_primary_source_urls_columns:
                cur.execute(
                    """
                    UPDATE story_research
                    SET
                        research_data = %s,
                        status = %s,
                        completed_at = now(),
                        primary_sources = %s,
                        primary_source_urls = %s
                    WHERE id = %s
                    """,
                    (json.dumps(research_data), status, primary_sources, primary_source_urls, research_id),
                )
            elif self.has_primary_sources_columns:
                cur.execute(
                    """
                    UPDATE story_research
                    SET
                        research_data = %s,
                        status = %s,
                        completed_at = now(),
                        primary_sources = %s
                    WHERE id = %s
                    """,
                    (json.dumps(research_data), status, primary_sources, research_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE story_research
                    SET
                        research_data = %s,
                        status = %s,
                        completed_at = now()
                    WHERE id = %s
                    """,
                    (json.dumps(research_data), status, research_id),
                )
        self.conn.commit()

    def fetch_completed_missing_primary_sources(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetches completed story_research rows whose research_data is missing
        a non-empty `primary_sources` array (or whose column is empty).
        Used for one-time backfills.
        """
        select_primary_cols = ""
        where_missing = ""

        if self.has_primary_sources_columns:
            select_primary_cols = ", sr.primary_sources, sr.primary_source_urls"
            where_missing = """
              AND (
                    sr.primary_sources IS NULL
              )
            """
        else:
            where_missing = """
              AND sr.research_data IS NOT NULL
              AND (
                    sr.research_data->'primary_sources' IS NULL
                    OR jsonb_typeof(sr.research_data->'primary_sources') <> 'array'
                    OR (
                        jsonb_typeof(sr.research_data->'primary_sources') = 'array'
                        AND jsonb_array_length(sr.research_data->'primary_sources') = 0
                    )
              )
            """

        query = f"""
            SELECT
                sr.id as research_id,
                sr.lead_id,
                sr.research_data,
                l.url as lead_url,
                l.title as lead_title
                {select_primary_cols}
            FROM story_research sr
            JOIN leads l ON sr.lead_id = l.id
            WHERE sr.status = 'completed'
            {where_missing}
            ORDER BY sr.completed_at DESC NULLS LAST
        """
        if limit:
            query += f" LIMIT {int(limit)}"

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query)
            return cur.fetchall()

    def fetch_completed_empty_primary_sources(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetches completed story_research rows where primary_sources exists but is an empty array.
        These are the rows we want to audit (did we truly have no citations/URLs to extract?).
        """
        if not self.has_primary_sources_columns:
            raise RuntimeError(
                "primary_sources column does not exist on public.story_research."
            )

        query = """
            SELECT
                sr.id as research_id,
                sr.lead_id,
                sr.research_data,
                sr.primary_sources,
                sr.primary_source_urls,
                l.url as lead_url,
                l.title as lead_title
            FROM story_research sr
            JOIN leads l ON sr.lead_id = l.id
            WHERE sr.status = 'completed'
              AND sr.primary_sources IS NOT NULL
              AND sr.primary_sources = '{}'::text[]
            ORDER BY sr.completed_at DESC NULLS LAST
        """
        if limit:
            query += f" LIMIT {int(limit)}"

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query)
            return cur.fetchall()

    def overwrite_research_data(self, research_id: str, research_data: Dict[str, Any]) -> None:
        """
        Overwrites research_data without changing status/completed_at.
        Useful for backfilling new JSON keys on already-completed rows.
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE story_research
                SET research_data = %s
                WHERE id = %s
            """, (json.dumps(research_data), research_id))
        self.conn.commit()

    def update_primary_sources_columns(
        self,
        research_id: str,
        primary_sources: List[str],
        primary_source_urls: Optional[List[str]] = None,
    ) -> None:
        """
        Updates the new primary_sources / primary_source_urls columns.
        Requires the columns to exist.
        """
        if not self.has_primary_sources_columns:
            raise RuntimeError(
                "primary_sources column does not exist on public.story_research. "
                "Run the Supabase ALTER TABLE first."
            )

        with self.conn.cursor() as cur:
            if self.has_primary_source_urls_columns:
                cur.execute(
                    """
                    UPDATE story_research
                    SET primary_sources = %s,
                        primary_source_urls = %s
                    WHERE id = %s
                    """,
                    (primary_sources, primary_source_urls, research_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE story_research
                    SET primary_sources = %s
                    WHERE id = %s
                    """,
                    (primary_sources, research_id),
                )
        self.conn.commit()

    def update_status(self, research_id: str, status: str):
        """
        Updates just the status.
        """
        with self.conn.cursor() as cur:
            if status == 'in_progress':
                cur.execute("""
                    UPDATE story_research 
                    SET status = %s, started_at = now()
                    WHERE id = %s
                """, (status, research_id))
            else:
                cur.execute("""
                    UPDATE story_research 
                    SET status = %s
                    WHERE id = %s
                """, (status, research_id))
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()
