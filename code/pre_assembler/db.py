"""
Database connection and queries for the Pre-Assembler.
"""

import os
import uuid
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
                        COALESCE(sg.approved_for_assembly, FALSE) as approved_for_assembly,
                        sg.instagram_caption,
                        sg.hashtags,
                        sg.created_at,
                        
                        -- Count slides
                        (SELECT COUNT(*) FROM story_slides ss WHERE ss.story_generation_id = sg.id) as slide_count,
                        
                        -- Count approved photos
                        (SELECT COUNT(*) FROM story_photos sp 
                         WHERE sp.story_research_id = sg.story_research_id 
                         AND sp.status = 'approved') as photo_count,
                        
                        -- Prefer the editor's chosen thumbnail (persisted in the latest assembly JSON),
                        -- falling back to the thumbnail-generator selection (story_thumbnails.is_selected).
                        --
                        -- NOTE: We validate the JSON value with a uuid regex to avoid cast errors.
                        (SELECT
                            CASE
                                WHEN (sa.assembly_data->>'selected_thumbnail_id') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                                THEN (sa.assembly_data->>'selected_thumbnail_id')::uuid
                                ELSE NULL
                            END
                         FROM story_assemblies sa
                         WHERE sa.story_generation_id = sg.id
                         ORDER BY sa.updated_at DESC
                         LIMIT 1) as assembly_selected_thumbnail_id,

                        -- Fallback thumbnail (selected/most recent generated)
                        (SELECT st.id FROM story_thumbnails st
                         WHERE st.story_generation_id = sg.id
                         AND st.status IN ('generated', 'approved')
                         ORDER BY st.is_selected DESC, st.created_at DESC
                         LIMIT 1) as fallback_thumbnail_id,
                        
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
                         LIMIT 1) as assembly_updated_at,

                        -- Get full assembly data for title/subtitle overrides
                        (SELECT sa.assembly_data FROM story_assemblies sa
                         WHERE sa.story_generation_id = sg.id
                         ORDER BY sa.updated_at DESC
                         LIMIT 1) as assembly_data
                        
                    FROM story_generations sg
                    JOIN story_research sr ON sg.story_research_id = sr.id
                    WHERE sr.status = 'completed'
                )
                SELECT 
                    ss.story_generation_id,
                    ss.story_research_id,
                    ss.hook_title,
                    ss.subtitle,
                    ss.domain_tag,
                    ss.is_enabled,
                    ss.approved_for_assembly,
                    ss.instagram_caption,
                    ss.hashtags,
                    ss.slide_count,
                    ss.photo_count,
                    COALESCE(
                        (SELECT st2.id
                         FROM story_thumbnails st2
                         WHERE st2.story_generation_id = ss.story_generation_id
                           AND st2.id = ss.assembly_selected_thumbnail_id
                         LIMIT 1),
                        ss.fallback_thumbnail_id
                    ) as thumbnail_id,
                    ss.thumbnail_count,
                    COALESCE(ss.assembly_status, 'new') as assembly_status,
                    ss.created_at,
                    ss.assembly_updated_at as updated_at,
                    ss.assembly_data
                FROM story_stats ss
                WHERE slide_count > 0
                  AND thumbnail_count > 0
                  AND (assembly_status IS NULL OR assembly_status != 'finalized')
                  -- Hide anything already published by the scheduler
                  AND NOT EXISTS (
                      SELECT 1
                      FROM scheduled_posts sp
                      WHERE sp.story_generation_id = ss.story_generation_id
                        AND sp.status = 'published'
                  )
                ORDER BY 
                    approved_for_assembly ASC,
                    is_enabled DESC,
                    CASE 
                        WHEN assembly_status = 'in_progress' THEN 1
                        WHEN assembly_status = 'draft' THEN 2
                        ELSE 3
                    END,
                    created_at DESC
            """
            cur.execute(query)
            rows = cur.fetchall()
            
            # Post-process: Override title/subtitle/domain_tag from assembly cover slide if available
            for row in rows:
                ad = row.get('assembly_data')
                if ad and isinstance(ad, dict) and 'slides' in ad:
                    # Find cover slide
                    for slide in ad['slides']:
                        if isinstance(slide, dict) and slide.get('type') == 'cover':
                            content = slide.get('content') or {}
                            if content.get('title'):
                                row['hook_title'] = content['title']
                            if content.get('subtitle'):
                                row['subtitle'] = content['subtitle']
                            if content.get('domain_tag'):
                                row['domain_tag'] = content['domain_tag']
                            break
                # Clean up to avoid sending heavy JSON downstream if not needed (though main.py filters fields)
                if 'assembly_data' in row:
                    del row['assembly_data']
            
            return rows
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
                    COALESCE(sg.approved_for_assembly, FALSE) as approved_for_assembly,
                    sg.generation_metadata,
                    sg.instagram_caption,
                    sg.hashtags,
                    sg.created_at,
                    sr.research_data,
                    sr.primary_sources,
                    sr.primary_source_urls,
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
                SELECT id, image_url, caption, source_attribution, concept_tag, metadata
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


def get_story_queue_ids(*, only_unapproved: bool = True) -> list[str]:
    """
    Return ordered story_generation_ids for the "ready for assembly" queue.

    Ordering mirrors `get_stories_ready_for_assembly()`.
    By default, returns only unapproved stories (so the editor can "approve -> next").
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                WITH story_stats AS (
                    SELECT
                        sg.id as story_generation_id,
                        COALESCE(sg.is_enabled, TRUE) as is_enabled,
                        COALESCE(sg.approved_for_assembly, FALSE) as approved_for_assembly,
                        sg.created_at,
                        -- Check thumbnail count
                        (SELECT COUNT(*) FROM story_thumbnails st
                         WHERE st.story_generation_id = sg.id
                         AND st.status IN ('generated', 'approved')) as thumbnail_count,
                        -- Count slides
                        (SELECT COUNT(*) FROM story_slides ss WHERE ss.story_generation_id = sg.id) as slide_count,
                        -- Check assembly status
                        (SELECT sa.status FROM story_assemblies sa
                         WHERE sa.story_generation_id = sg.id
                         ORDER BY sa.updated_at DESC
                         LIMIT 1) as assembly_status
                    FROM story_generations sg
                    JOIN story_research sr ON sg.story_research_id = sr.id
                    WHERE sr.status = 'completed'
                )
                SELECT
                    story_generation_id
                FROM story_stats
                WHERE slide_count > 0
                  AND thumbnail_count > 0
                  AND (assembly_status IS NULL OR assembly_status != 'finalized')
                  AND (%s = FALSE OR approved_for_assembly = FALSE)
                ORDER BY
                    approved_for_assembly ASC,
                    is_enabled DESC,
                    CASE
                        WHEN assembly_status = 'in_progress' THEN 1
                        WHEN assembly_status = 'draft' THEN 2
                        ELSE 3
                    END,
                    created_at DESC
            """
            cur.execute(query, (bool(only_unapproved),))
            rows = cur.fetchall() or []
            return [str(r["story_generation_id"]) for r in rows if r.get("story_generation_id")]
    except Exception as e:
        logger.error(f"Error fetching story queue ids: {e}")
        return []
    finally:
        conn.close()


def get_next_story_generation_id(current_story_generation_id: str, *, only_unapproved: bool = True) -> str | None:
    """
    Given a current story_generation_id, return the next story_generation_id in the queue.
    """
    ids = get_story_queue_ids(only_unapproved=only_unapproved)
    if not ids:
        return None
    try:
        idx = ids.index(str(current_story_generation_id))
    except ValueError:
        # If current isn't in the queue (e.g., already approved), just return the first.
        return ids[0] if ids else None
    nxt = idx + 1
    return ids[nxt] if nxt < len(ids) else None


def update_story_generation(
    story_generation_id: str,
    *,
    hook_title: str | None = None,
    subtitle: str | None = None,
    domain_tag: str | None = None,
    is_enabled: bool | None = None,
    approved_for_assembly: bool | None = None,
) -> dict | None:
    """
    Update a story_generations row (title/subtitle/domain_tag/is_enabled).
    Returns the updated row fields we care about, or None if not found.
    """
    # Nothing to update
    if hook_title is None and subtitle is None and domain_tag is None and is_enabled is None and approved_for_assembly is None:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        hook_title,
                        subtitle,
                        domain_tag,
                        COALESCE(is_enabled, TRUE) as is_enabled,
                        COALESCE(approved_for_assembly, FALSE) as approved_for_assembly,
                        approved_for_assembly_at
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
    if approved_for_assembly is not None:
        sets.append("approved_for_assembly = %s")
        params.append(approved_for_assembly)
        sets.append("approved_for_assembly_at = CASE WHEN %s THEN NOW() ELSE NULL END")
        params.append(approved_for_assembly)

    params.append(story_generation_id)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE story_generations
                SET {", ".join(sets)}
                WHERE id = %s
                RETURNING
                    id,
                    hook_title,
                    subtitle,
                    domain_tag,
                    COALESCE(is_enabled, TRUE) as is_enabled,
                    COALESCE(approved_for_assembly, FALSE) as approved_for_assembly,
                    approved_for_assembly_at
                """,
                tuple(params),
            )
            row = cur.fetchone()
            conn.commit()
            updated = dict(row) if row else None

            # Best-effort: when a story is approved_for_assembly=True, ensure there's at least
            # one draft assembly row so the Scheduler can pick it up immediately.
            try:
                if approved_for_assembly is True and updated:
                    ensure_default_assembly_exists(str(story_generation_id))
            except Exception as e:
                logger.error(f"Failed to ensure default assembly for {story_generation_id}: {e}")

            return updated
    except Exception as e:
        logger.error(f"Error updating story_generation {story_generation_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


# =============================================================================
# Scheduler Integration Helpers
# =============================================================================

def _distribute_photos(text_count: int, photo_count: int) -> list[int]:
    """
    Spread photos evenly among text slides.
    Returns list of text-slide indices after which to insert photos.
    """
    if photo_count <= 0 or text_count <= 0:
        return []
    positions: list[int] = []
    interval = text_count / (photo_count + 1)
    for i in range(photo_count):
        pos = int((i + 1) * interval) - 1
        pos = max(0, min(pos, text_count - 1))
        positions.append(pos)
    return positions


def _generate_default_assembly_data(story_data: dict) -> dict:
    """
    Generate a default assembly JSON (same idea as `pre_assembler.main.generate_default_assembly`)
    so approved stories can be scheduled even before a user opens the editor.
    """
    story = story_data.get("story") or {}
    slides = story_data.get("slides") or []
    photos = story_data.get("photos") or []
    thumbnails = story_data.get("thumbnails") or []

    # Pick selected thumbnail (or first)
    selected_thumb = None
    for t in thumbnails:
        if isinstance(t, dict) and t.get("is_selected"):
            selected_thumb = t
            break
    if not selected_thumb and thumbnails:
        selected_thumb = thumbnails[0] if isinstance(thumbnails[0], dict) else None

    domain_tag = story.get("domain_tag")

    assembly_slides: list[dict] = []

    # 1) Cover
    assembly_slides.append(
        {
            "id": str(uuid.uuid4()),
            "type": "cover",
            "template": "cover3",
            "visible": True,
            "content": {
                "title": story.get("hook_title"),
                "subtitle": story.get("subtitle"),
                "thumbnail_url": (selected_thumb or {}).get("image_url") if selected_thumb else None,
                "thumbnail_zoom": 1.0,
                "thumbnail_offset_x": 0.0,
                "thumbnail_offset_y": 0.0,
                "domain_tag": domain_tag,
            },
        }
    )

    # 2) Text slides (+ photos placed using story_photos.metadata.placement when available)
    generation_id = str(story.get("story_generation_id") or story.get("id") or "")

    def _get_photo_placement(p: dict) -> tuple[int, bool]:
        meta = p.get("metadata") if isinstance(p.get("metadata"), dict) else {}
        placement = meta.get("placement") if isinstance(meta, dict) else None
        if isinstance(placement, dict) and str(placement.get("generation_id") or "") == generation_id:
            try:
                after = int(placement.get("after_slide_order", 0) or 0)
            except Exception:
                after = 0
            enabled = bool(placement.get("enabled", False))
            return after, enabled
        return -1, False

    fallback_positions = _distribute_photos(len(slides), len(photos))
    fallback_after_orders = [(int(pos) + 1) for pos in fallback_positions]

    placements: list[dict] = []
    any_enabled = False
    for idx, p in enumerate(photos):
        after, enabled = _get_photo_placement(p)
        if after < 0:
            after = fallback_after_orders[idx] if idx < len(fallback_after_orders) else len(slides)
            enabled = False
        after = max(0, min(int(after), len(slides)))
        placements.append({"photo": p, "after": after, "enabled": enabled})
        any_enabled = any_enabled or bool(enabled)

    if placements and not any_enabled:
        placements[0]["enabled"] = True

    photos_by_after: dict[int, list[dict]] = {}
    for item in placements:
        photos_by_after.setdefault(int(item["after"]), []).append(item)

    # after_slide_order=0 → after cover, before slide 1
    for item in photos_by_after.get(0, []):
        p = item["photo"]
        if isinstance(p, dict):
            assembly_slides.append(
                {
                    "id": str(uuid.uuid4()),
                    "type": "photo",
                    "template": "photos1",
                    "visible": bool(item.get("enabled")),
                    "content": {
                        "image_url": p.get("image_url"),
                        "caption": p.get("caption") or "",
                        "source": p.get("source_attribution") or "",
                        "domain_tag": domain_tag,
                    },
                    "source_photo_id": str(p.get("id")) if p.get("id") else None,
                }
            )

    for i, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        assembly_slides.append(
            {
                "id": str(uuid.uuid4()),
                "type": "text",
                "template": "editorial3",
                "visible": True,
                "content": {
                    "text": slide.get("text_content"),
                    "paragraph_count": slide.get("paragraph_count"),
                    "domain_tag": domain_tag,
                },
                "source_slide_id": str(slide.get("id")) if slide.get("id") else None,
            }
        )

        slide_order = int(slide.get("slide_order") or (i + 1))
        for item in photos_by_after.get(slide_order, []):
            p = item["photo"]
            if isinstance(p, dict):
                assembly_slides.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "photo",
                        "template": "photos1",
                        "visible": bool(item.get("enabled")),
                        "content": {
                            "image_url": p.get("image_url"),
                            "caption": p.get("caption") or "",
                            "source": p.get("source_attribution") or "",
                            "domain_tag": domain_tag,
                        },
                        "source_photo_id": str(p.get("id")) if p.get("id") else None,
                    }
                )

    # 3) Closing slide
    assembly_slides.append(
        {
            "id": str(uuid.uuid4()),
            "type": "text",
            "template": "closing1",
            "visible": True,
            "content": {
                "primary_sources": story.get("primary_sources") or [],
                "primary_source_urls": story.get("primary_source_urls") or [],
                "domain_tag": domain_tag,
            },
        }
    )

    now_iso = datetime.now().isoformat()
    return {
        "version": 1,
        "story_generation_id": str(story.get("story_generation_id") or story.get("id") or ""),
        "slides": assembly_slides,
        "metadata": {"created_at": now_iso, "updated_at": now_iso, "hydrated_from_story": True, "hydrated_at": now_iso},
    }


def ensure_default_assembly_exists(story_generation_id: str) -> None:
    """
    Ensure at least one story_assemblies row exists for this story_generation_id.
    If none exists, create a default draft assembly.
    """
    existing = get_assembly(story_generation_id)
    if existing:
        return
    story_data = get_story_full_data(story_generation_id)
    if not story_data:
        raise ValueError(f"Story not found for assembly creation: {story_generation_id}")
    assembly_data = _generate_default_assembly_data(story_data)
    save_assembly(story_generation_id, assembly_data, status="draft")


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


# =============================================================================
# Deletion
# =============================================================================

def delete_story_generation(story_generation_id: str) -> dict:
    """
    Permanently delete a story_generation and its dependent rows.

    Order matters due to foreign keys:
    - scheduled_posts (scheduler)
    - story_assemblies
    - story_thumbnails
    - story_slides
    - story_generations
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # scheduled_posts (if scheduler already touched it)
            cur.execute(
                "DELETE FROM scheduled_posts WHERE story_generation_id = %s",
                (story_generation_id,),
            )
            scheduled_deleted = cur.rowcount or 0

            cur.execute(
                "DELETE FROM story_assemblies WHERE story_generation_id = %s",
                (story_generation_id,),
            )
            assemblies_deleted = cur.rowcount or 0

            cur.execute(
                "DELETE FROM story_thumbnails WHERE story_generation_id = %s",
                (story_generation_id,),
            )
            thumbs_deleted = cur.rowcount or 0

            cur.execute(
                "DELETE FROM story_slides WHERE story_generation_id = %s",
                (story_generation_id,),
            )
            slides_deleted = cur.rowcount or 0

            cur.execute(
                "DELETE FROM story_generations WHERE id = %s",
                (story_generation_id,),
            )
            sg_deleted = cur.rowcount or 0

            conn.commit()
            return {
                "story_generation_id": str(story_generation_id),
                "deleted": bool(sg_deleted),
                "rows": {
                    "scheduled_posts": int(scheduled_deleted),
                    "story_assemblies": int(assemblies_deleted),
                    "story_thumbnails": int(thumbs_deleted),
                    "story_slides": int(slides_deleted),
                    "story_generations": int(sg_deleted),
                },
            }
    except Exception as e:
        conn.rollback()
        logger.error(f"Error deleting story_generation {story_generation_id}: {e}")
        raise
    finally:
        conn.close()

