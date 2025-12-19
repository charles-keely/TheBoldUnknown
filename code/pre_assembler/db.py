"""
Database connection and queries for the Pre-Assembler.
"""

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
        connect_timeout = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))  # seconds
        statement_timeout_ms = int(os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS", "15000"))
        
        # Fallback: Construct DATABASE_URL from individual POSTGRES_* vars
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

        # Prevent "infinite loading" when DB is unreachable by applying:
        # - connect_timeout: fail fast during TCP connect / SSL handshake
        # - statement_timeout: fail slow queries fast (server-side)
        #
        # NOTE: statement_timeout is best-effort; it requires server support.
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


# =============================================================================
# Story Queries
# =============================================================================

def get_stories_ready_for_assembly():
    """
    Fetches all stories that have:
    - Completed story_research
    - At least 1 story_generation
    - At least 1 story_slide
    - At least 1 generated story_thumbnail
    - NOT finalized in story_assemblies
    
    Returns list of story summaries for the dashboard.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                WITH story_stats AS (
                    SELECT 
                        sg.id as story_generation_id,
                        sg.story_research_id,
                        sg.hook_title,
                        sg.subtitle,
                        sg.domain_tag,
                        COALESCE(sg.is_enabled, TRUE) as is_enabled,
                        sg.instagram_caption,
                        sg.hashtags,
                        sg.created_at,
                        
                        -- Count slides
                        (SELECT COUNT(*) FROM story_slides ss WHERE ss.story_generation_id = sg.id) as slide_count,
                        
                        -- Count approved photos
                        (SELECT COUNT(*) FROM story_photos sp 
                         WHERE sp.story_research_id = sg.story_research_id 
                         AND sp.status = 'approved') as photo_count,
                        
                        -- Get selected or first thumbnail ID (we'll construct URL in app)
                        (SELECT st.id FROM story_thumbnails st 
                         WHERE st.story_generation_id = sg.id 
                         AND st.status IN ('generated', 'approved')
                         ORDER BY st.is_selected DESC, st.created_at DESC 
                         LIMIT 1) as thumbnail_id,
                        
                        -- Check thumbnail count
                        (SELECT COUNT(*) FROM story_thumbnails st 
                         WHERE st.story_generation_id = sg.id 
                         AND st.status IN ('generated', 'approved')) as thumbnail_count,
                        
                        -- Check assembly status
                        (SELECT sa.status FROM story_assemblies sa 
                         WHERE sa.story_generation_id = sg.id 
                         ORDER BY sa.updated_at DESC 
                         LIMIT 1) as assembly_status,
                         
                        -- Get assembly updated_at
                        (SELECT sa.updated_at FROM story_assemblies sa 
                         WHERE sa.story_generation_id = sg.id 
                         ORDER BY sa.updated_at DESC 
                         LIMIT 1) as assembly_updated_at
                        
                    FROM story_generations sg
                    JOIN story_research sr ON sg.story_research_id = sr.id
                    WHERE sr.status = 'completed'
                )
                SELECT 
                    story_generation_id,
                    story_research_id,
                    hook_title,
                    subtitle,
                    domain_tag,
                    is_enabled,
                    instagram_caption,
                    hashtags,
                    slide_count,
                    photo_count,
                    thumbnail_id,
                    thumbnail_count,
                    COALESCE(assembly_status, 'new') as assembly_status,
                    created_at,
                    assembly_updated_at as updated_at
                FROM story_stats
                WHERE slide_count > 0
                  AND thumbnail_count > 0
                  AND (assembly_status IS NULL OR assembly_status != 'finalized')
                ORDER BY 
                    is_enabled DESC,
                    CASE 
                        WHEN assembly_status = 'in_progress' THEN 1
                        WHEN assembly_status = 'draft' THEN 2
                        ELSE 3
                    END,
                    created_at DESC
            """
            cur.execute(query)
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching stories ready for assembly: {e}")
        return []
    finally:
        conn.close()


def get_story_full_data(story_generation_id: str):
    """
    Fetches complete data for a story including:
    - Story generation info
    - All story slides
    - All approved photos
    - All thumbnails
    - All alternative generations (for title/subtitle switching)
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Get the story generation
            cur.execute("""
                SELECT 
                    sg.id as story_generation_id,
                    sg.story_research_id,
                    sg.hook_title,
                    sg.subtitle,
                    sg.domain_tag,
                    COALESCE(sg.is_enabled, TRUE) as is_enabled,
                    sg.generation_metadata,
                    sg.instagram_caption,
                    sg.hashtags,
                    sg.created_at,
                    sr.research_data,
                    l.title as lead_title
                FROM story_generations sg
                JOIN story_research sr ON sg.story_research_id = sr.id
                JOIN leads l ON sr.lead_id = l.id
                WHERE sg.id = %s
            """, (story_generation_id,))
            story = cur.fetchone()
            
            if not story:
                return None
            
            story_research_id = story['story_research_id']

            # Title/subtitle alternatives live inside generation_metadata (text_generator stores
            # all options there, with a selected_id).
            gm = story.get("generation_metadata") or {}
            options = []
            if isinstance(gm, dict):
                options = gm.get("options") or []

            generations = []
            if isinstance(options, list):
                for opt in options:
                    if not isinstance(opt, dict):
                        continue
                    opt_id = opt.get("id")
                    generations.append(
                        {
                            "id": str(opt_id) if opt_id is not None else "",
                            "hook_title": opt.get("title") or opt.get("hook_title") or "",
                            "subtitle": opt.get("subtitle") or "",
                            "domain_tag": opt.get("domain_tag") or opt.get("tag") or "",
                        }
                    )
            # Fallback: if no options were recorded, expose the current story columns as a single option.
            if not generations:
                generations = [
                    {
                        "id": str((gm.get("selected_id") if isinstance(gm, dict) else None) or "selected"),
                        "hook_title": story.get("hook_title") or "",
                        "subtitle": story.get("subtitle") or "",
                        "domain_tag": story.get("domain_tag") or "",
                    }
                ]
            
            # Get all slides for this generation
            cur.execute("""
                SELECT id, slide_order, text_content, document_type_tag, paragraph_count
                FROM story_slides
                WHERE story_generation_id = %s
                ORDER BY slide_order
            """, (story_generation_id,))
            slides = cur.fetchall()
            
            # Get all approved photos for this research
            cur.execute("""
                SELECT id, image_url, caption, source_attribution, concept_tag
                FROM story_photos
                WHERE story_research_id = %s AND status = 'approved'
                ORDER BY created_at
            """, (story_research_id,))
            photos = cur.fetchall()
            
            # Get all thumbnails for this generation (id is used to construct image URL)
            cur.execute("""
                SELECT id, concept_number, concept_type, is_selected, status
                FROM story_thumbnails
                WHERE story_generation_id = %s AND status IN ('generated', 'approved')
                ORDER BY concept_number
            """, (story_generation_id,))
            thumbnails = cur.fetchall()
            
            # Add image_url for each thumbnail (constructed from id)
            for t in thumbnails:
                t['image_url'] = f"/api/thumbnails/{t['id']}/image"
            
            return {
                'story': dict(story),
                'generations': generations,
                'slides': [dict(s) for s in slides],
                'photos': [dict(p) for p in photos],
                'thumbnails': [dict(t) for t in thumbnails]
            }
    except Exception as e:
        logger.error(f"Error fetching story full data for {story_generation_id}: {e}")
        return None
    finally:
        conn.close()


def get_story_caption_and_hashtags(story_generation_id: str) -> dict | None:
    """
    Fetch just instagram_caption + hashtags for a story generation.
    Useful for debugging and for lightweight reads.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id as story_generation_id,
                    instagram_caption,
                    hashtags,
                    created_at
                FROM story_generations
                WHERE id = %s
                """,
                (story_generation_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error fetching caption/hashtags for {story_generation_id}: {e}")
        return None
    finally:
        conn.close()


def update_story_generation(
    story_generation_id: str,
    *,
    hook_title: str | None = None,
    subtitle: str | None = None,
    domain_tag: str | None = None,
    is_enabled: bool | None = None,
) -> dict | None:
    """
    Update a story_generations row (title/subtitle/domain_tag/is_enabled).
    Returns the updated row fields we care about, or None if not found.
    """
    # Nothing to update
    if hook_title is None and subtitle is None and domain_tag is None and is_enabled is None:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, hook_title, subtitle, domain_tag, COALESCE(is_enabled, TRUE) as is_enabled
                    FROM story_generations
                    WHERE id = %s
                    """,
                    (story_generation_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    sets: list[str] = []
    params: list[object] = []

    if hook_title is not None:
        sets.append("hook_title = %s")
        params.append(hook_title)
    if subtitle is not None:
        sets.append("subtitle = %s")
        params.append(subtitle)
    if domain_tag is not None:
        sets.append("domain_tag = %s")
        params.append(domain_tag)
    if is_enabled is not None:
        sets.append("is_enabled = %s")
        params.append(is_enabled)

    params.append(story_generation_id)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE story_generations
                SET {", ".join(sets)}
                WHERE id = %s
                RETURNING id, hook_title, subtitle, domain_tag, COALESCE(is_enabled, TRUE) as is_enabled
                """,
                tuple(params),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error updating story_generation {story_generation_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db_fingerprint() -> dict:
    """
    Return a non-sensitive DB fingerprint to confirm which DB this API is connected to.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    current_database() as database,
                    current_schema() as schema,
                    current_user as user,
                    version() as version,
                    now() as now
                """
            )
            row = cur.fetchone()
            return dict(row) if row else {}
    except Exception as e:
        logger.error(f"Error fetching DB fingerprint: {e}")
        return {"error": str(e)}
    finally:
        conn.close()


# =============================================================================
# Assembly Queries
# =============================================================================

def get_assembly(story_generation_id: str):
    """
    Fetches the most recent assembly for a story.
    Returns None if no assembly exists.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, story_generation_id, assembly_data, status, created_at, updated_at
                FROM story_assemblies
                WHERE story_generation_id = %s
                ORDER BY updated_at DESC
                LIMIT 1
            """, (story_generation_id,))
            return cur.fetchone()
    except Exception as e:
        logger.error(f"Error fetching assembly for {story_generation_id}: {e}")
        return None
    finally:
        conn.close()


def save_assembly(story_generation_id: str, assembly_data: dict, status: str = 'draft'):
    """
    Saves or updates an assembly for a story.
    If an assembly exists, updates it. Otherwise creates a new one.
    Returns the assembly ID.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check if assembly exists
            cur.execute("""
                SELECT id FROM story_assemblies
                WHERE story_generation_id = %s
                ORDER BY updated_at DESC
                LIMIT 1
            """, (story_generation_id,))
            existing = cur.fetchone()
            
            if existing:
                # Update existing assembly
                cur.execute("""
                    UPDATE story_assemblies
                    SET assembly_data = %s::jsonb, status = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                """, (json.dumps(assembly_data), status, existing['id']))
                assembly_id = cur.fetchone()['id']
                logger.info(f"Updated assembly {assembly_id} for story {story_generation_id}")
            else:
                # Create new assembly
                cur.execute("""
                    INSERT INTO story_assemblies (story_generation_id, assembly_data, status)
                    VALUES (%s, %s::jsonb, %s)
                    RETURNING id
                """, (story_generation_id, json.dumps(assembly_data), status))
                assembly_id = cur.fetchone()['id']
                logger.info(f"Created assembly {assembly_id} for story {story_generation_id}")
            
            conn.commit()
            return assembly_id
    except Exception as e:
        logger.error(f"Error saving assembly for {story_generation_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def update_assembly_status(assembly_id: str, status: str):
    """
    Updates just the status of an assembly.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE story_assemblies
                SET status = %s, updated_at = NOW()
                WHERE id = %s
            """, (status, assembly_id))
            conn.commit()
            logger.info(f"Updated assembly {assembly_id} status to {status}")
    except Exception as e:
        logger.error(f"Error updating assembly status: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


# =============================================================================
# Utility Functions
# =============================================================================

def check_db_connection():
    """
    Test database connection.
    Returns True if successful, False otherwise.
    """
    try:
        conn = get_db_connection()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False

