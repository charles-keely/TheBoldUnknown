import psycopg2
from psycopg2.extras import RealDictCursor
import json
from typing import List, Dict, Any, Optional
from .config import config

class Database:
    def __init__(self):
        self.conn = psycopg2.connect(config.DATABASE_URL)

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
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE story_research 
                SET 
                    research_data = %s,
                    status = %s,
                    completed_at = now()
                WHERE id = %s
            """, (json.dumps(research_data), status, research_id))
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
