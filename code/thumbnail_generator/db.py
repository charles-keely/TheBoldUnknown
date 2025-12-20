import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor, Json
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
        
        # Fallback: Construct DATABASE_URL from individual POSTGRES_* vars
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
            raise ValueError("DATABASE_URL environment variable is not set")
            
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


def get_stories_needing_thumbnails(limit=None):
    """
    Fetches story_generations that don't have any usable thumbnails yet.
    "Usable" means at least one thumbnail in status ('generated', 'approved').
    This includes stories where thumbnails exist but are all 'failed' (or otherwise non-usable),
    so reruns can recover.
    Returns list of dicts with generation info and research data.
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
                    sr.research_data,
                    l.title as lead_title,
                    l.summary as lead_summary
                FROM story_generations sg
                JOIN story_research sr ON sg.story_research_id = sr.id
                JOIN leads l ON sr.lead_id = l.id
                LEFT JOIN story_thumbnails st
                  ON sg.id = st.story_generation_id
                 AND st.status IN ('generated', 'approved')
                WHERE st.id IS NULL
                ORDER BY sg.created_at DESC
            """
            if limit:
                query += f" LIMIT {int(limit)}"
            
            cur.execute(query)
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching stories needing thumbnails: {e}")
        return []
    finally:
        conn.close()


def get_story_generation(generation_id):
    """
    Fetches a specific story_generation with its research data.
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
                    sr.research_data,
                    l.title as lead_title,
                    l.summary as lead_summary
                FROM story_generations sg
                JOIN story_research sr ON sg.story_research_id = sr.id
                JOIN leads l ON sr.lead_id = l.id
                WHERE sg.id = %s
            """
            cur.execute(query, (generation_id,))
            return cur.fetchone()
    except Exception as e:
        logger.error(f"Error fetching story generation {generation_id}: {e}")
        return None
    finally:
        conn.close()


def save_thumbnail(generation_id, concept_number, concept_type, scene_description, 
                   full_prompt, generation_metadata=None):
    """
    Creates a thumbnail record in pending status.
    Returns the thumbnail ID.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                INSERT INTO story_thumbnails 
                (id, story_generation_id, concept_number, concept_type, scene_description, 
                 full_prompt, status, generation_metadata, created_at)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, 'pending', %s, NOW())
                RETURNING id
            """
            cur.execute(query, (
                generation_id,
                concept_number,
                concept_type,
                scene_description,
                full_prompt,
                Json(generation_metadata) if generation_metadata else None
            ))
            thumbnail_id = cur.fetchone()['id']
            conn.commit()
            logger.info(f"Created thumbnail record {thumbnail_id} for generation {generation_id}")
            return thumbnail_id
    except Exception as e:
        logger.error(f"Error saving thumbnail: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_thumbnail_for_story_concept(generation_id, concept_number):
    """
    Fetch the most recent thumbnail row for a given story + concept_number.
    (If duplicates exist from older runs, we prefer the newest.)
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT *
                FROM story_thumbnails
                WHERE story_generation_id = %s AND concept_number = %s
                ORDER BY created_at DESC
                LIMIT 1
            """
            cur.execute(query, (generation_id, concept_number))
            return cur.fetchone()
    except Exception as e:
        logger.error(f"Error fetching thumbnail for generation {generation_id} concept {concept_number}: {e}")
        return None
    finally:
        conn.close()


def update_thumbnail_content(
    thumbnail_id,
    *,
    concept_type=None,
    scene_description=None,
    full_prompt=None,
    generation_metadata=None,
    reset_image=True,
):
    """
    Update the "content" fields for an existing thumbnail row (prompt/metadata/etc).
    Used to make reruns idempotent instead of creating duplicate rows.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            set_clauses = []
            params = []

            if concept_type is not None:
                set_clauses.append("concept_type = %s")
                params.append(concept_type)
            if scene_description is not None:
                set_clauses.append("scene_description = %s")
                params.append(scene_description)
            if full_prompt is not None:
                set_clauses.append("full_prompt = %s")
                params.append(full_prompt)
            if generation_metadata is not None:
                set_clauses.append("generation_metadata = %s")
                params.append(Json(generation_metadata))

            # On rerun, we want to regenerate, so clear out old image + timestamps.
            set_clauses.append("status = 'pending'")
            if reset_image:
                set_clauses.append("image_url = NULL")
                set_clauses.append("generated_at = NULL")

            if not set_clauses:
                return

            query = f"""
                UPDATE story_thumbnails
                SET {", ".join(set_clauses)}
                WHERE id = %s
            """
            params.append(thumbnail_id)
            cur.execute(query, tuple(params))
            conn.commit()
            logger.info(f"Updated thumbnail {thumbnail_id} content (reset pending)")
    except Exception as e:
        logger.error(f"Error updating thumbnail {thumbnail_id} content: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def update_thumbnail_status(thumbnail_id, status, image_url=None, error_message=None, metadata_update=None):
    """
    Updates the status and optionally the image_url of a thumbnail.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Build a single UPDATE based on which optional fields are present.
            set_clauses = ["status = %s"]
            params = [status]

            if image_url is not None:
                set_clauses.append("image_url = %s")
                params.append(image_url)
                if status == "generated":
                    set_clauses.append("generated_at = NOW()")

            meta_patch = {}
            if error_message:
                meta_patch["error"] = error_message
            if metadata_update:
                meta_patch.update(metadata_update)

            if meta_patch:
                set_clauses.append("generation_metadata = COALESCE(generation_metadata, '{}'::jsonb) || %s")
                params.append(Json(meta_patch))

            query = f"""
                UPDATE story_thumbnails
                SET {", ".join(set_clauses)}
                WHERE id = %s
            """
            params.append(thumbnail_id)
            cur.execute(query, tuple(params))
            
            conn.commit()
            logger.info(f"Updated thumbnail {thumbnail_id} status to {status}")
    except Exception as e:
        logger.error(f"Error updating thumbnail {thumbnail_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def select_thumbnail(thumbnail_id):
    """
    Marks a thumbnail as selected (and unselects any other for the same story).
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # First, get the story_generation_id for this thumbnail
            cur.execute(
                "SELECT story_generation_id FROM story_thumbnails WHERE id = %s",
                (thumbnail_id,)
            )
            result = cur.fetchone()
            if not result:
                raise ValueError(f"Thumbnail {thumbnail_id} not found")
            
            generation_id = result['story_generation_id']
            
            # Unselect all thumbnails for this story
            cur.execute(
                """
                UPDATE story_thumbnails 
                SET is_selected = FALSE, selected_at = NULL
                WHERE story_generation_id = %s
                """,
                (generation_id,)
            )
            
            # Select the specified thumbnail
            cur.execute(
                """
                UPDATE story_thumbnails 
                SET is_selected = TRUE, selected_at = NOW()
                WHERE id = %s
                """,
                (thumbnail_id,)
            )
            
            conn.commit()
            logger.info(f"Selected thumbnail {thumbnail_id} for generation {generation_id}")
    except Exception as e:
        logger.error(f"Error selecting thumbnail {thumbnail_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_thumbnails_for_story(generation_id):
    """
    Fetches all thumbnails for a given story generation.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT *
                FROM story_thumbnails
                WHERE story_generation_id = %s
                ORDER BY concept_number
            """
            cur.execute(query, (generation_id,))
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching thumbnails for generation {generation_id}: {e}")
        return []
    finally:
        conn.close()


def get_pending_thumbnails():
    """
    Fetches thumbnails that are pending generation.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT *
                FROM story_thumbnails
                WHERE status = 'pending'
                ORDER BY created_at
            """
            cur.execute(query)
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching pending thumbnails: {e}")
        return []
    finally:
        conn.close()
