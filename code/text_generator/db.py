import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from dotenv import load_dotenv
import logging

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
        
        # Fallback: Construct DATABASE_URL from individual POSTGRES_* vars if available
        if not db_url:
            host = os.getenv("POSTGRES_HOST")
            port = os.getenv("POSTGRES_PORT", "5432")
            dbname = os.getenv("POSTGRES_DB")
            user = os.getenv("POSTGRES_USER")
            password = os.getenv("POSTGRES_PASSWORD")
            
            if host and dbname and user and password:
                db_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
                logger.info("Constructed DATABASE_URL from individual env vars.")
            
        if not db_url:
            logger.error(f"Current working dir: {os.getcwd()}")
            logger.error(f"Script dir: {current_dir}")
            logger.error(f"Root dir: {root_dir}")
            logger.error(f"Env vars keys: {list(os.environ.keys())}")
            raise ValueError("DATABASE_URL environment variable is not set")
            
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def get_completed_research(limit=None, story_id=None):
    """
    Fetches story_research items that are 'completed'.
    If story_id is provided, fetches that specific story (regardless of generation status).
    If story_id is None, fetches completed stories that haven't been generated yet.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if story_id:
                query = """
                    SELECT sr.id, sr.research_data, l.url as lead_url 
                    FROM story_research sr
                    JOIN leads l ON sr.lead_id = l.id
                    WHERE sr.id = %s
                """
                cur.execute(query, (story_id,))
            else:
                # We want research that is completed, but NOT yet in story_generations
                query = """
                    SELECT sr.id, sr.research_data, l.url as lead_url 
                    FROM story_research sr
                    JOIN leads l ON sr.lead_id = l.id
                    LEFT JOIN story_generations sg ON sr.id = sg.story_research_id
                    WHERE sr.status = 'completed' 
                    AND sg.id IS NULL
                """
                if limit:
                    query += f" LIMIT {int(limit)}"
                cur.execute(query)
            
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching completed research: {e}")
        return []
    finally:
        conn.close()

def get_approved_photos(story_research_id):
    """
    Fetches approved photos for a given story.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT id, description, search_query, image_url
                FROM story_photos
                WHERE story_research_id = %s
                AND status = 'approved'
            """
            cur.execute(query, (story_research_id,))
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching approved photos for story {story_research_id}: {e}")
        return []
    finally:
        conn.close()

def save_story_generation(story_id, selected_data, full_generation_data):
    """
    Saves the cover text and metadata.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                INSERT INTO story_generations 
                (story_research_id, hook_title, subtitle, domain_tag, generation_metadata, model_used)
                VALUES (%s, %s, %s, %s, %s, 'gpt-5.2')
                RETURNING id
            """
            cur.execute(query, (
                story_id,
                selected_data['title'],
                selected_data['subtitle'],
                selected_data['domain_tag'],
                Json(full_generation_data)
            ))
            gen_id = cur.fetchone()['id']
            conn.commit()
            return gen_id
    except Exception as e:
        logger.error(f"Error saving story generation for story {story_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def save_story_slides(generation_id, slides):
    """
    Saves the narrative slides.
    slides: list of dicts { 'text': ..., 'tag': ... }
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                INSERT INTO story_slides 
                (story_generation_id, slide_order, text_content, document_type_tag, paragraph_count)
                VALUES (%s, %s, %s, %s, %s)
            """
            values = []
            for idx, slide in enumerate(slides):
                # Simple heuristic for paragraph count
                para_count = slide['text'].count('\n\n') + 1
                values.append((
                    generation_id,
                    idx + 1,
                    slide['text'],
                    slide['tag'],
                    para_count
                ))
            
            cur.executemany(query, values)
            conn.commit()
    except Exception as e:
        logger.error(f"Error saving slides for generation {generation_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def update_photo_text(photo_id, caption, source, concept_tag):
    """
    Updates a photo with generated text.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                UPDATE story_photos
                SET caption = %s,
                    source_attribution = %s,
                    concept_tag = %s,
                    text_generated_at = NOW()
                WHERE id = %s
            """
            cur.execute(query, (caption, source, concept_tag, photo_id))
            conn.commit()
    except Exception as e:
        logger.error(f"Error updating photo {photo_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
