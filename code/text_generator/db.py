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

def get_completed_research(limit=None, story_id=None, random=False):
    """
    Fetches story_research items that are 'completed'.
    If story_id is provided, fetches that specific story (regardless of generation status).
    If story_id is None:
        - If random is True, fetches a random completed story (generated or not).
        - If random is False, fetches completed stories that haven't been generated yet.
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
            elif random:
                # Random completed story, regardless of generation status
                query = """
                    SELECT sr.id, sr.research_data, l.url as lead_url 
                    FROM story_research sr
                    JOIN leads l ON sr.lead_id = l.id
                    WHERE sr.status = 'completed'
                    ORDER BY RANDOM()
                    LIMIT 1
                """
                cur.execute(query)
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


def update_caption_and_hashtags(generation_id, caption, hashtags):
    """
    Updates a story_generation with Instagram caption and hashtags.
    hashtags: list of strings (e.g., ["#TheBoldUnknown", "#Curiosity", ...])
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                UPDATE story_generations
                SET instagram_caption = %s,
                    hashtags = %s
                WHERE id = %s
            """
            cur.execute(query, (caption, hashtags, generation_id))
            conn.commit()
            logger.info(f"Updated caption and hashtags for generation {generation_id}")
    except Exception as e:
        logger.error(f"Error updating caption/hashtags for generation {generation_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_stories_needing_captions(limit=None):
    """
    Fetches story_generations that don't have instagram_caption yet.
    Returns list of dicts with generation info and slides.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT 
                    sg.id as generation_id,
                    sg.hook_title,
                    sg.subtitle,
                    sg.domain_tag,
                    sg.story_research_id
                FROM story_generations sg
                WHERE sg.instagram_caption IS NULL
                ORDER BY sg.created_at ASC
            """
            if limit:
                query += f" LIMIT {int(limit)}"
            
            cur.execute(query)
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching stories needing captions: {e}")
        return []
    finally:
        conn.close()


def get_story_generation_with_slides(generation_id):
    """
    Fetches a story_generation with its slides for caption/hashtag generation.
    Returns dict with generation info and slides list.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Get generation info
            gen_query = """
                SELECT 
                    sg.id as generation_id,
                    sg.hook_title,
                    sg.subtitle,
                    sg.domain_tag,
                    sg.story_research_id
                FROM story_generations sg
                WHERE sg.id = %s
            """
            cur.execute(gen_query, (generation_id,))
            generation = cur.fetchone()
            
            if not generation:
                return None
            
            # Get slides
            slides_query = """
                SELECT text_content as text, document_type_tag as tag
                FROM story_slides
                WHERE story_generation_id = %s
                ORDER BY slide_order ASC
            """
            cur.execute(slides_query, (generation_id,))
            slides = cur.fetchall()
            
            return {
                'generation_id': generation['generation_id'],
                'hook_title': generation['hook_title'],
                'subtitle': generation['subtitle'],
                'domain_tag': generation['domain_tag'],
                'story_research_id': generation['story_research_id'],
                'slides': [dict(s) for s in slides]
            }
    except Exception as e:
        logger.error(f"Error fetching generation with slides {generation_id}: {e}")
        return None
    finally:
        conn.close()


def get_stories_with_existing_generations(limit=None):
    """
    Fetches story_research items that ALREADY have story_generations.
    Used for regeneration workflows.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT sr.id, sr.research_data, l.url as lead_url,
                       sg.id as generation_id
                FROM story_research sr
                JOIN leads l ON sr.lead_id = l.id
                JOIN story_generations sg ON sr.id = sg.story_research_id
                WHERE sr.status = 'completed'
                AND sg.is_enabled = true
                ORDER BY sg.created_at ASC
            """
            if limit:
                query += f" LIMIT {int(limit)}"
            cur.execute(query)
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching stories with existing generations: {e}")
        return []
    finally:
        conn.close()


def delete_generation_and_slides(generation_id):
    """
    Deletes a story_generation and its associated slides.
    Used before regenerating text content.
    Checks for assemblies/thumbnails first and skips if they exist.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check for story_assemblies that reference this generation
            cur.execute("SELECT COUNT(*) as count FROM story_assemblies WHERE story_generation_id = %s", (generation_id,))
            assembly_count = cur.fetchone()['count']
            if assembly_count > 0:
                logger.warning(f"Generation {generation_id} has {assembly_count} assembly(ies) - skipping deletion")
                return False
            
            # Check for story_thumbnails that reference this generation
            cur.execute("SELECT COUNT(*) as count FROM story_thumbnails WHERE story_generation_id = %s", (generation_id,))
            thumbnail_count = cur.fetchone()['count']
            if thumbnail_count > 0:
                logger.warning(f"Generation {generation_id} has {thumbnail_count} thumbnail(s) - skipping deletion")
                return False
            
            # First delete slides (foreign key constraint)
            cur.execute("DELETE FROM story_slides WHERE story_generation_id = %s", (generation_id,))
            slides_deleted = cur.rowcount
            
            # Then delete the generation
            cur.execute("DELETE FROM story_generations WHERE id = %s", (generation_id,))
            
            conn.commit()
            logger.info(f"Deleted generation {generation_id} and {slides_deleted} slides")
            return True
    except Exception as e:
        logger.error(f"Error deleting generation {generation_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
