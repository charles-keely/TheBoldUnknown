import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from tenacity import retry, stop_after_attempt, wait_exponential
from config import Config
from utils.logger import logger

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
