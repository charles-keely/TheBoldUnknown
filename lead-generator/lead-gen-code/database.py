import psycopg2
from psycopg2.extras import RealDictCursor
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

db = Database()
