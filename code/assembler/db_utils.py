import os
import logging
import json
import psycopg
from psycopg.rows import dict_row
from contextlib import contextmanager
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)

load_dotenv(os.path.join(current_dir, '.env'))
load_dotenv(os.path.join(root_dir, '.env'))
load_dotenv()

def get_db_connection():
    """Establishes and returns a database connection."""
    try:
        db_url = os.getenv("DATABASE_URL")
        connect_timeout = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))
        statement_timeout_ms = int(os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS", "15000"))
        
        if not db_url:
            host = os.getenv("POSTGRES_HOST")
            port = os.getenv("POSTGRES_PORT", "5432")
            dbname = os.getenv("POSTGRES_DB")
            user = os.getenv("POSTGRES_USER")
            password = os.getenv("POSTGRES_PASSWORD")
            
            if host and dbname and user and password:
                db_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
            
        if not db_url:
            raise ValueError("DATABASE_URL environment variable is not set")

        conn = psycopg.connect(
            db_url,
            connect_timeout=connect_timeout,
            options=f"-c statement_timeout={statement_timeout_ms}",
            row_factory=dict_row,
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

@contextmanager
def get_db_cursor():
    """Context manager for database cursor with automatic cleanup."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            yield cur
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_pending_assemblies(*, story_generation_id: str | None = None, limit: int | None = None):
    """
    Fetch stories that are approved for assembly but not yet finalized.
    Also fetches the assembly_data if it exists.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # We want stories that are approved_for_assembly = true
            # AND either don't have an assembly entry, or have one that isn't finalized.
            # Ideally, the pre-assembler creates the assembly record.
            # So we join story_generations with story_assemblies.
            
            where_extra = ""
            params: list[object] = []
            if story_generation_id:
                where_extra = " AND sg.id = %s"
                params.append(story_generation_id)

            limit_sql = ""
            if isinstance(limit, int) and limit > 0:
                limit_sql = f" LIMIT {int(limit)}"

            query = f"""
                SELECT 
                    sg.id as story_generation_id,
                    sg.hook_title,
                    sa.id as assembly_id,
                    sa.assembly_data,
                    sa.status as assembly_status
                FROM story_generations sg
                LEFT JOIN story_assemblies sa ON sg.id = sa.story_generation_id
                WHERE sg.approved_for_assembly = TRUE
                  AND (sa.status IS NULL OR sa.status != 'finalized')
                {where_extra}
                ORDER BY sg.created_at ASC
                {limit_sql}
            """
            cur.execute(query, tuple(params))
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching pending assemblies: {e}")
        return []
    finally:
        conn.close()

def mark_assembly_finalized(story_generation_id: str, file_paths: list[str]):
    """
    Update the assembly status to finalized and save the rendered file paths.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # First check if assembly exists, if not create it (though unusual for this flow)
            cur.execute("SELECT id FROM story_assemblies WHERE story_generation_id = %s", (story_generation_id,))
            existing = cur.fetchone()
            
            if existing:
                cur.execute("""
                    UPDATE story_assemblies
                    SET status = 'finalized', 
                        rendered_files = %s::jsonb,
                        updated_at = NOW()
                    WHERE story_generation_id = %s
                """, (json.dumps(file_paths), story_generation_id))
            else:
                # Should have been created by pre-assembler, but handle gracefully?
                # For now assuming it exists or we skip.
                logger.warning(f"No assembly found for {story_generation_id} when marking finalized.")
                
            conn.commit()
    except Exception as e:
        logger.error(f"Error marking assembly finalized: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def get_thumbnail_data(thumbnail_id: str):
    """
    Fetch thumbnail base64 data from the database.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT generation_metadata FROM story_thumbnails WHERE id = %s", (thumbnail_id,))
            row = cur.fetchone()
            if row and row['generation_metadata']:
                return row['generation_metadata'].get('image_base64')
            return None
    except Exception as e:
        logger.error(f"Error fetching thumbnail data: {e}")
        return None
    finally:
        conn.close()

