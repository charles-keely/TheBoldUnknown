import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import List, Dict, Any
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

    def fetch_candidates(self, since_date: datetime) -> List[Dict[str, Any]]:
        """
        Fetches all candidates created after the given date that are not rejected or already published.
        """
        query = """
            SELECT 
                id, title, url, summary, 
                brand_score, virality_score, viral_hook,
                created_at, source_origin
            FROM leads
            WHERE created_at > %s
            AND status NOT IN ('rejected', 'published')
            ORDER BY created_at DESC
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (since_date,))
            return cur.fetchall()

    def update_lead_status(self, lead_id: str, status: str):
        """
        Updates the status of a lead.
        """
        with self.conn.cursor() as cur:
            cur.execute("UPDATE leads SET status = %s WHERE id = %s", (status, lead_id))
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()

