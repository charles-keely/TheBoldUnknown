import psycopg2
from psycopg2.extras import RealDictCursor, Json
import json
from .config import config

class Database:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
            dbname=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD
        )
        self.conn.autocommit = True
        self._init_tables()

    def _init_tables(self):
        with self.conn.cursor() as cur:
            # Create story_photos table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS story_photos (
                    id uuid NOT NULL DEFAULT gen_random_uuid(),
                    story_research_id uuid NOT NULL,
                    image_url text NOT NULL,
                    source_page_url text,
                    search_query text,
                    description text,
                    relevance_score integer CHECK (relevance_score >= 0 AND relevance_score <= 10),
                    verifiability_score integer CHECK (verifiability_score >= 0 AND verifiability_score <= 10),
                    status text DEFAULT 'potential' CHECK (status = ANY (ARRAY['potential', 'approved', 'rejected'])),
                    metadata jsonb DEFAULT '{}',
                    created_at timestamp with time zone DEFAULT now(),
                    CONSTRAINT story_photos_pkey PRIMARY KEY (id),
                    CONSTRAINT story_photos_story_research_id_fkey FOREIGN KEY (story_research_id) REFERENCES story_research(id)
                );
            """)

    def fetch_stories_needing_photos(self, limit=5):
        """
        Finds completed stories that don't have enough approved photos yet.
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT sr.*, l.title, l.url as original_url
                FROM story_research sr
                JOIN leads l ON sr.lead_id = l.id
                WHERE sr.status = 'completed'
                AND (
                    SELECT count(*) 
                    FROM story_photos sp 
                    WHERE sp.story_research_id = sr.id 
                    AND sp.status = 'approved'
                ) < 2
                ORDER BY random()
                LIMIT %s;
            """, (limit,))
            return cur.fetchall()

    def save_photo_candidate(self, story_id, image_data):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO story_photos 
                (story_research_id, image_url, source_page_url, search_query, description, relevance_score, verifiability_score, metadata, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """, (
                story_id,
                image_data.get('image_url'),
                image_data.get('source_page_url'),
                image_data.get('search_query'),
                image_data.get('description'),
                image_data.get('relevance_score'),
                image_data.get('verifiability_score'),
                Json(image_data.get('metadata', {})),
                image_data.get('status', 'potential')
            ))
            return cur.fetchone()[0]

    def close(self):
        self.conn.close()
