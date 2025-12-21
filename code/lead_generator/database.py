import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from tenacity import retry, stop_after_attempt, wait_exponential
from config import Config
from utils.logger import logger
from datetime import datetime, timezone

class Database:
    def __init__(self):
        self.conn = None

    def connect(self):
        if self.conn is None or self.conn.closed:
            try:
                self.conn = psycopg2.connect(
                    host=Config.POSTGRES_HOST,
                    port=Config.POSTGRES_PORT,
                    dbname=Config.POSTGRES_DB,
                    user=Config.POSTGRES_USER,
                    password=Config.POSTGRES_PASSWORD
                )
                logger.info("Connected to database")
            except Exception as e:
                logger.warning(f"Database connection failed (will retry if inside logic): {e}")
                raise

    def get_cursor(self):
        self.connect()
        return self.conn.cursor(cursor_factory=RealDictCursor)

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def execute_query(self, query, params=None):
        try:
            with self.get_cursor() as cur:
                cur.execute(query, params)
                self.conn.commit()
                return cur
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            logger.error(f"Query execution failed: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def fetch_one(self, query, params=None):
        try:
            with self.get_cursor() as cur:
                cur.execute(query, params)
                return cur.fetchone()
        except Exception as e:
            logger.warning(f"Fetch one failed: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def fetch_all(self, query, params=None):
        try:
            with self.get_cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Fetch all failed: {e}")
            raise

    # --- Business Logic Methods ---

    def check_url_exists(self, url: str) -> bool:
        query = "SELECT count(*) as count FROM processed_urls WHERE url = %s"
        result = self.fetch_one(query, (url,))
        return result['count'] > 0

    def mark_url_processed(self, url: str):
        query = "INSERT INTO processed_urls (url) VALUES (%s) ON CONFLICT DO NOTHING"
        self.execute_query(query, (url,))

    def check_similarity(self, embedding: list[float], threshold: float = 0.85) -> bool:
        """
        Checks if a similar lead exists. 
        """
        distance_threshold = 1 - threshold
        query = """
        SELECT 1 
        FROM leads 
        WHERE embedding <=> %s < %s 
        LIMIT 1
        """
        embedding_str = str(embedding)
        result = self.fetch_one(query, (embedding_str, distance_threshold))
        return result is not None

    # -------------------------------------------------------------------------
    # Durable semantic dedupe ("story memory")
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_dedupe_text(*, title: str | None, summary: str | None, url: str | None) -> str:
        """
        Canonical text used for embeddings. Keep it stable so re-embedding is deterministic.
        """
        t = (title or "").strip()
        s = (summary or "").strip()
        u = (url or "").strip()
        parts = []
        if t:
            parts.append(f"TITLE: {t}")
        if s:
            parts.append(f"SUMMARY: {s}")
        if u:
            parts.append(f"URL: {u}")
        return "\n".join(parts).strip() or (t or s or u or "")

    def check_story_memory_similarity(
        self,
        embedding: list[float],
        *,
        threshold: float = 0.85,
        source_types: list[str] | None = None,
    ) -> dict | None:
        """
        Checks if a semantically similar story exists in the durable `story_memory` index.

        Returns:
          A matching row (dict) if found, else None.
        """
        distance_threshold = 1 - float(threshold)
        embedding_str = str(embedding)

        if source_types:
            query = """
            SELECT source_type, source_id, lead_id, canonical_title, canonical_url, updated_at
            FROM story_memory
            WHERE embedding IS NOT NULL
              AND is_active_for_dedupe = TRUE
              AND source_type = ANY(%s::text[])
              AND embedding <=> %s < %s
            ORDER BY embedding <=> %s ASC
            LIMIT 1
            """
            params = (source_types, embedding_str, distance_threshold, embedding_str)
        else:
            query = """
            SELECT source_type, source_id, lead_id, canonical_title, canonical_url, updated_at
            FROM story_memory
            WHERE embedding IS NOT NULL
              AND is_active_for_dedupe = TRUE
              AND embedding <=> %s < %s
            ORDER BY embedding <=> %s ASC
            LIMIT 1
            """
            params = (embedding_str, distance_threshold, embedding_str)

        return self.fetch_one(query, params)

    def upsert_story_memory_item(
        self,
        *,
        source_type: str,
        source_id: str,
        lead_id: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        url: str | None = None,
        embedding: list[float] | None = None,
    ) -> None:
        """
        Upsert a story_memory row keyed by (source_type, source_id).
        """
        dedupe_text = self._build_dedupe_text(title=title, summary=summary, url=url)
        embedding_str = str(embedding) if embedding else None
        now = datetime.now(timezone.utc)

        query = """
        INSERT INTO story_memory (
          source_type, source_id, lead_id,
          canonical_title, canonical_summary, canonical_url,
          dedupe_text, embedding, is_active_for_dedupe, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, TRUE, %s, %s)
        ON CONFLICT (source_type, source_id)
        DO UPDATE SET
          lead_id = COALESCE(EXCLUDED.lead_id, story_memory.lead_id),
          canonical_title = COALESCE(EXCLUDED.canonical_title, story_memory.canonical_title),
          canonical_summary = COALESCE(EXCLUDED.canonical_summary, story_memory.canonical_summary),
          canonical_url = COALESCE(EXCLUDED.canonical_url, story_memory.canonical_url),
          dedupe_text = EXCLUDED.dedupe_text,
          embedding = COALESCE(EXCLUDED.embedding, story_memory.embedding),
          updated_at = EXCLUDED.updated_at
        """
        self.execute_query(
            query,
            (
                source_type,
                source_id,
                lead_id,
                title,
                summary,
                url,
                dedupe_text,
                embedding_str,
                now,
                now,
            ),
        )

    # ---- Backfill helpers (used by CLI sync command) ----

    def fetch_leads_missing_story_memory(self, *, limit: int = 500) -> list[dict]:
        """
        Return leads that are not yet present in story_memory as source_type='lead'.
        """
        query = """
        SELECT l.id::text as lead_id, l.title, l.summary, l.url
        FROM leads l
        WHERE NOT EXISTS (
          SELECT 1 FROM story_memory sm
          WHERE sm.source_type = 'lead' AND sm.source_id = l.id
        )
        ORDER BY l.created_at DESC
        LIMIT %s
        """
        return self.fetch_all(query, (int(limit),))

    def fetch_story_generations_missing_story_memory(self, *, limit: int = 500) -> list[dict]:
        """
        Return story_generations that are not yet present in story_memory as source_type='story_generation'.
        """
        query = """
        SELECT
          sg.id::text as story_generation_id,
          l.id::text as lead_id,
          l.title,
          l.summary,
          l.url
        FROM story_generations sg
        JOIN story_research sr ON sg.story_research_id = sr.id
        JOIN leads l ON sr.lead_id = l.id
        WHERE NOT EXISTS (
          SELECT 1 FROM story_memory sm
          WHERE sm.source_type = 'story_generation' AND sm.source_id = sg.id
        )
        ORDER BY sg.created_at DESC
        LIMIT %s
        """
        return self.fetch_all(query, (int(limit),))

    def fetch_finalized_assemblies_missing_story_memory(self, *, limit: int = 500) -> list[dict]:
        """
        Return finalized story_assemblies not yet in story_memory as source_type='story_assembly'.
        """
        query = """
        SELECT
          sa.id::text as assembly_id,
          sg.id::text as story_generation_id,
          l.id::text as lead_id,
          l.title,
          l.summary,
          l.url
        FROM story_assemblies sa
        JOIN story_generations sg ON sa.story_generation_id = sg.id
        JOIN story_research sr ON sg.story_research_id = sr.id
        JOIN leads l ON sr.lead_id = l.id
        WHERE sa.status = 'finalized'
          AND NOT EXISTS (
            SELECT 1 FROM story_memory sm
            WHERE sm.source_type = 'story_assembly' AND sm.source_id = sa.id
          )
        ORDER BY sa.updated_at DESC
        LIMIT %s
        """
        return self.fetch_all(query, (int(limit),))

    def fetch_published_posts_missing_story_memory(self, *, limit: int = 500) -> list[dict]:
        """
        Return published scheduled_posts not yet in story_memory as source_type='scheduled_post'.
        """
        query = """
        SELECT
          sp.id::text as post_id,
          sp.story_generation_id::text as story_generation_id,
          l.id::text as lead_id,
          l.title,
          l.summary,
          l.url
        FROM scheduled_posts sp
        JOIN story_generations sg ON sp.story_generation_id = sg.id
        JOIN story_research sr ON sg.story_research_id = sr.id
        JOIN leads l ON sr.lead_id = l.id
        WHERE sp.status = 'published'
          AND NOT EXISTS (
            SELECT 1 FROM story_memory sm
            WHERE sm.source_type = 'scheduled_post' AND sm.source_id = sp.id
          )
        ORDER BY sp.published_at DESC NULLS LAST, sp.updated_at DESC
        LIMIT %s
        """
        return self.fetch_all(query, (int(limit),))

    def insert_lead(self, lead: dict) -> str:
        query = """
        INSERT INTO leads (title, url, summary, embedding, brand_score, virality_score, source_origin, published_at, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'new')
        RETURNING id
        """
        embedding_str = str(lead['embedding'])
        
        # We use execute_query directly to get the ID back
        # Note: execute_query returns the cursor
        with self.get_cursor() as cur:
            cur.execute(query, (
                lead['title'],
                lead['url'],
                lead['summary'],
                embedding_str,
                lead['brand_score'],
                lead['virality_score'],
                lead['source_origin'],
                lead.get('published_at')
            ))
            lead_id = cur.fetchone()['id']
            self.conn.commit()
            return str(lead_id)

    def get_active_discovery_topics(self) -> list[dict]:
        query = """
        SELECT * FROM discovery_topics 
        WHERE status = 'active' 
        ORDER BY last_searched_at ASC NULLS FIRST 
        LIMIT 1
        """
        return self.fetch_all(query)

    def update_topic_last_searched(self, topic_id: str):
        query = """
        UPDATE discovery_topics 
        SET last_searched_at = NOW() 
        WHERE id = %s
        """
        self.execute_query(query, (topic_id,))

    def insert_discovery_topics(self, topics: list[dict]):
        """
        topics: list of dicts with 'topic' and 'origin_lead_id'
        """
        if not topics:
            return
            
        query = """
        INSERT INTO discovery_topics (topic, origin_lead_id) 
        VALUES %s 
        ON CONFLICT (topic) DO NOTHING
        """
        values = [(t['topic'], t['origin_lead_id']) for t in topics]
        
        with self.get_cursor() as cur:
            execute_values(cur, query, values)
            self.conn.commit()

db = Database()
