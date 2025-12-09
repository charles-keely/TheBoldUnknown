import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from config import config
from utils.logger import logger
import contextlib

@contextlib.contextmanager
def get_db_connection():
    """
    Context manager for database connections.
    """
    conn = None
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        yield conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise
    finally:
        if conn:
            conn.close()

class Database:
    def __init__(self):
        pass

    def check_url_exists(self, url: str) -> bool:
        query = "SELECT count(*) as count FROM processed_urls WHERE url = %s"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (url,))
                result = cur.fetchone()
                return result[0] > 0

    def mark_url_processed(self, url: str):
        query = "INSERT INTO processed_urls (url) VALUES (%s) ON CONFLICT DO NOTHING"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (url,))
            conn.commit()

    def check_similarity(self, embedding: list[float], threshold: float = 0.90) -> bool:
        """
        Checks if a similar lead exists. 
        Returns True if a similar lead exists (similarity > threshold), False otherwise.
        """
        # Note: <-> is Euclidean distance, <=> is Cosine distance.
        # We want Cosine Similarity. 
        # cosine_similarity = 1 - cosine_distance
        # So we want: 1 - (embedding <=> other) > threshold
        # Which means: (embedding <=> other) < 1 - threshold
        
        # However, the pgvector operator <=> returns cosine distance (1 - cosine_similarity).
        # So if we want similarity > 0.90, we want distance < 0.10.
        
        distance_threshold = 1 - threshold
        
        query = """
        SELECT 1 
        FROM leads 
        WHERE embedding <=> %s < %s 
        LIMIT 1
        """
        # pgvector expects a string representation of the vector like '[1,2,3]'
        embedding_str = str(embedding)
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (embedding_str, distance_threshold))
                result = cur.fetchone()
                return result is not None

    def insert_lead(self, lead: dict) -> str:
        query = """
        INSERT INTO leads (title, url, summary, embedding, brand_score, virality_score, source_origin, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'new')
        RETURNING id
        """
        embedding_str = str(lead['embedding'])
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (
                    lead['title'],
                    lead['url'],
                    lead['summary'],
                    embedding_str,
                    lead['brand_score'],
                    lead['virality_score'],
                    lead['source_origin']
                ))
                lead_id = cur.fetchone()[0]
            conn.commit()
            return str(lead_id)

    def get_active_discovery_topics(self) -> list[dict]:
        query = """
        SELECT * FROM discovery_topics 
        WHERE status = 'active' 
        ORDER BY last_searched_at ASC NULLS FIRST 
        LIMIT 1
        """
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query)
                return cur.fetchall()

    def update_topic_last_searched(self, topic_id: str):
        query = """
        UPDATE discovery_topics 
        SET last_searched_at = NOW() 
        WHERE id = %s
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (topic_id,))
            conn.commit()

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
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, query, values)
            conn.commit()

db = Database()
