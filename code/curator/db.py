import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from .config import config


class Database:
    def __init__(self):
        self.conn = psycopg2.connect(config.DATABASE_URL)

    def get_latest_cutoff_date(self) -> datetime:
        """
        Finds the created_at date of the most recently published story.
        If no stories are published, returns 7 days ago.
        """
        with self.conn.cursor() as cur:
            cur.execute("SELECT MAX(created_at) FROM leads WHERE status = 'published'")
            result = cur.fetchone()
            if result and result[0]:
                return result[0]
            return datetime.now() - timedelta(days=7)

    def fetch_candidates(self, since_date: datetime, strategy: str = None) -> List[Dict[str, Any]]:
        """
        Fetches all candidates created after the given date that are not rejected or already published.
        """
        strategy = strategy or config.CURATION_STRATEGY
        
        order_clause = "ORDER BY created_at DESC"
        if strategy == "virality":
            order_clause = "ORDER BY virality_score DESC NULLS LAST"
        elif strategy == "composite":
            order_clause = "ORDER BY (COALESCE(virality_score, 0) + COALESCE(brand_score, 0)) DESC"
            
        query = f"""
            SELECT 
                id, title, url, summary, 
                brand_score, virality_score, viral_hook,
                created_at, source_origin
            FROM leads
            WHERE created_at > %s
            AND status NOT IN ('rejected', 'published')
            {{order_clause}}
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query.format(order_clause=order_clause), (since_date,))
            return cur.fetchall()

    def clear_queued_stories(self, since_date: datetime) -> int:
        """
        Resets 'approved' leads with 'queued' research tasks back to 'new' 
        and removes them from the research queue.
        Only affects items created after since_date.
        """
        with self.conn.cursor() as cur:
            # Identify target IDs - items that are approved and queued within the timeframe
            cur.execute("""
                SELECT l.id 
                FROM leads l
                JOIN story_research sr ON l.id = sr.lead_id
                WHERE l.created_at > %s
                  AND l.status = 'approved'
                  AND sr.status = 'queued'
            """, (since_date,))
            rows = cur.fetchall()
            
            if not rows:
                return 0
                
            lead_ids = [str(row[0]) for row in rows]
            
            # Delete from story_research
            cur.execute("DELETE FROM story_research WHERE lead_id = ANY(%s::uuid[])", (lead_ids,))
            
            # Reset leads to 'new'
            cur.execute("UPDATE leads SET status = 'new' WHERE id = ANY(%s::uuid[])", (lead_ids,))
            
        self.conn.commit()
        return len(lead_ids)

    def update_lead_status(self, lead_id: str, status: str) -> bool:
        """
        Updates the status of a lead. Returns True if a row was found and updated.
        """
        with self.conn.cursor() as cur:
            cur.execute("UPDATE leads SET status = %s WHERE id = %s", (status, lead_id))
            updated = cur.rowcount > 0
        self.conn.commit()
        return updated

    def queue_story_for_research(self, lead_id: str, notes: Optional[str] = None):
        """
        Ensure the given lead is present in the story_research queue.

        - If no row exists for this lead, insert one with status 'queued'.
        - If a row already exists (e.g., previously skipped or re-queued),
          update the status back to 'queued' and refresh created_at.
        - Optionally stores curator reasoning as notes for the researcher.
        """
        query = """
            INSERT INTO story_research (lead_id, status, notes)
            VALUES (%s, 'queued', %s)
            ON CONFLICT (lead_id) DO UPDATE
            SET status = 'queued',
                notes = COALESCE(EXCLUDED.notes, story_research.notes),
                created_at = now()
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (lead_id, notes))
        self.conn.commit()

    def rollback(self):
        """
        Rolls back the current transaction. Useful for recovering from errors.
        """
        if self.conn:
            self.conn.rollback()

    def close(self):
        if self.conn:
            self.conn.close()

