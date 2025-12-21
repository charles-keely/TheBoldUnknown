"""
Database operations for the Scheduler.
Handles scheduled_posts, schedule_approvals, and token management.
"""

import logging
import json
from datetime import datetime, date, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from .config import config

logger = logging.getLogger(__name__)


# =============================================================================
# Connection
# =============================================================================

def get_db_connection() -> psycopg.Connection:
    """Get a read-write database connection."""
    db_url = config.DATABASE_URL
    if not db_url:
        import os
        host = os.getenv("POSTGRES_HOST")
        port = os.getenv("POSTGRES_PORT", "5432")
        dbname = os.getenv("POSTGRES_DB")
        user = os.getenv("POSTGRES_USER")
        password = os.getenv("POSTGRES_PASSWORD")
        if host and dbname and user and password:
            db_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

    if not db_url:
        raise ValueError("DATABASE_URL is not set")

    conn = psycopg.connect(
        db_url,
        connect_timeout=config.POSTGRES_CONNECT_TIMEOUT,
        options=f"-c statement_timeout={config.POSTGRES_STATEMENT_TIMEOUT_MS}",
        row_factory=dict_row,
    )
    return conn


# =============================================================================
# Schedule Queries
# =============================================================================

def get_db_fingerprint() -> dict:
    """
    Non-sensitive DB fingerprint so we can confirm which DB the scheduler is connected to.
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
    finally:
        conn.close()


def debug_scheduler_state() -> dict:
    """
    Return counts that explain why scheduler sync may return 0.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*)::int as c FROM story_generations WHERE approved_for_assembly = TRUE")
            approved_total = int((cur.fetchone() or {}).get("c", 0))

            cur.execute(
                """
                SELECT COUNT(*)::int as c
                FROM story_generations
                WHERE approved_for_assembly = TRUE
                  AND COALESCE(is_enabled, TRUE) = TRUE
                """
            )
            approved_enabled = int((cur.fetchone() or {}).get("c", 0))

            cur.execute("SELECT COUNT(*)::int as c FROM scheduled_posts")
            scheduled_total = int((cur.fetchone() or {}).get("c", 0))

            cur.execute(
                """
                SELECT COUNT(*)::int as c
                FROM scheduled_posts
                WHERE status NOT IN ('published', 'failed')
                """
            )
            scheduled_active = int((cur.fetchone() or {}).get("c", 0))

            # The same eligibility logic used by `get_approved_stories_not_scheduled()`
            cur.execute(
                """
                WITH chosen_assembly AS (
                  SELECT DISTINCT ON (sa.story_generation_id)
                    sa.story_generation_id,
                    sa.id as assembly_id,
                    sa.status as assembly_status,
                    sa.updated_at as assembly_updated_at
                  FROM story_assemblies sa
                  WHERE sa.assembly_data IS NOT NULL
                  ORDER BY
                    sa.story_generation_id,
                    CASE WHEN sa.status = 'finalized' THEN 0 ELSE 1 END,
                    sa.updated_at DESC
                )
                SELECT COUNT(*)::int as c
                FROM story_generations sg
                JOIN chosen_assembly ca ON ca.story_generation_id = sg.id
                WHERE sg.approved_for_assembly = TRUE
                  AND COALESCE(sg.is_enabled, TRUE) = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM scheduled_posts sp
                      WHERE sp.story_generation_id = sg.id
                      AND sp.status NOT IN ('published', 'failed')
                  )
                """
            )
            eligible_to_schedule = int((cur.fetchone() or {}).get("c", 0))

            # Sample a few eligible ids for debugging
            cur.execute(
                """
                WITH chosen_assembly AS (
                  SELECT DISTINCT ON (sa.story_generation_id)
                    sa.story_generation_id,
                    sa.id as assembly_id,
                    sa.status as assembly_status,
                    sa.updated_at as assembly_updated_at
                  FROM story_assemblies sa
                  WHERE sa.assembly_data IS NOT NULL
                  ORDER BY
                    sa.story_generation_id,
                    CASE WHEN sa.status = 'finalized' THEN 0 ELSE 1 END,
                    sa.updated_at DESC
                )
                SELECT sg.id::text as story_generation_id, ca.assembly_id::text as assembly_id
                FROM story_generations sg
                JOIN chosen_assembly ca ON ca.story_generation_id = sg.id
                WHERE sg.approved_for_assembly = TRUE
                  AND COALESCE(sg.is_enabled, TRUE) = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM scheduled_posts sp
                      WHERE sp.story_generation_id = sg.id
                      AND sp.status NOT IN ('published', 'failed')
                  )
                ORDER BY COALESCE(sg.approved_for_assembly_at, sg.created_at) ASC
                LIMIT 5
                """
            )
            sample = [dict(r) for r in (cur.fetchall() or [])]

            return {
                "fingerprint": get_db_fingerprint(),
                "counts": {
                    "approved_total": approved_total,
                    "approved_enabled": approved_enabled,
                    "scheduled_total": scheduled_total,
                    "scheduled_active": scheduled_active,
                    "eligible_to_schedule": eligible_to_schedule,
                },
                "sample_eligible": sample,
            }
    finally:
        conn.close()


def get_scheduled_posts(
    *,
    include_published: bool = True,
    include_failed: bool = True,
    limit: int = 100,
) -> list[dict]:
    """
    Get all scheduled posts with story info for display.
    Orders by scheduled_at ascending (soonest first).
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            status_filter = ["scheduled", "approved", "publishing"]
            if include_published:
                status_filter.append("published")
            if include_failed:
                status_filter.append("failed")
            
            cur.execute(
                """
                SELECT 
                    sp.id,
                    sp.story_generation_id,
                    sp.assembly_id,
                    sp.scheduled_at,
                    sp.position,
                    sp.status,
                    sp.approved_at,
                    sp.published_at,
                    sp.instagram_media_id,
                    sp.error_message,
                    sp.retry_count,
                    sp.created_at,
                    sp.updated_at,
                    -- Prefer cover title/subtitle from the chosen assembly (reflects editor overrides),
                    -- otherwise fall back to story_generations columns.
                    COALESCE(sa.assembly_data #>> '{slides,0,content,title}', sg.hook_title) as hook_title,
                    COALESCE(sa.assembly_data #>> '{slides,0,content,subtitle}', sg.subtitle) as subtitle,
                    sg.domain_tag,
                    -- Get thumbnail URL
                    COALESCE(
                        -- Prefer the editor's selected_thumbnail_id from the assembly JSON (if valid uuid)
                        (SELECT '/api/thumbnails/' || st_sel.id || '/image'
                         FROM story_thumbnails st_sel
                         WHERE st_sel.story_generation_id = sg.id
                           AND st_sel.id = CASE
                             WHEN (sa.assembly_data->>'selected_thumbnail_id') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                             THEN (sa.assembly_data->>'selected_thumbnail_id')::uuid
                             ELSE NULL
                           END
                         LIMIT 1),
                        (SELECT '/api/thumbnails/' || st.id || '/image'
                         FROM story_thumbnails st
                         WHERE st.story_generation_id = sg.id
                         AND st.status IN ('generated', 'approved')
                         ORDER BY st.is_selected DESC, st.created_at DESC
                         LIMIT 1),
                        NULL
                    ) as thumbnail_url
                FROM scheduled_posts sp
                JOIN story_generations sg ON sp.story_generation_id = sg.id
                LEFT JOIN story_assemblies sa ON sa.id = sp.assembly_id
                WHERE sp.status = ANY(%s)
                ORDER BY 
                    CASE sp.status
                        WHEN 'failed' THEN 1
                        WHEN 'publishing' THEN 2
                        WHEN 'scheduled' THEN 3
                        WHEN 'approved' THEN 4
                        WHEN 'published' THEN 5
                    END,
                    sp.scheduled_at ASC
                LIMIT %s
                """,
                (status_filter, limit),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_schedule_counts() -> dict:
    """Get counts of posts by status."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'scheduled') as pending_count,
                    COUNT(*) FILTER (WHERE status = 'approved') as approved_count,
                    COUNT(*) FILTER (WHERE status = 'published') as published_count,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_count
                FROM scheduled_posts
                """
            )
            row = cur.fetchone()
            return dict(row) if row else {
                "pending_count": 0,
                "approved_count": 0,
                "published_count": 0,
                "failed_count": 0,
            }
    finally:
        conn.close()


def get_approved_stories_not_scheduled() -> list[dict]:
    """
    Get stories that are:
    - approved_for_assembly = true
    - Have an assembly (prefer finalized if present, otherwise latest draft/in_progress)
    - NOT already in scheduled_posts (or only have published/failed entries)
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH chosen_assembly AS (
                  SELECT DISTINCT ON (sa.story_generation_id)
                    sa.story_generation_id,
                    sa.id as assembly_id,
                    sa.status as assembly_status,
                    sa.updated_at as assembly_updated_at
                  FROM story_assemblies sa
                  WHERE sa.assembly_data IS NOT NULL
                  ORDER BY
                    sa.story_generation_id,
                    CASE WHEN sa.status = 'finalized' THEN 0 ELSE 1 END,
                    sa.updated_at DESC
                )
                SELECT 
                    sg.id as story_generation_id,
                    sg.hook_title,
                    sg.subtitle,
                    sg.domain_tag,
                    ca.assembly_id
                FROM story_generations sg
                JOIN chosen_assembly ca ON ca.story_generation_id = sg.id
                WHERE sg.approved_for_assembly = TRUE
                  AND COALESCE(sg.is_enabled, TRUE) = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM scheduled_posts sp
                      WHERE sp.story_generation_id = sg.id
                      AND sp.status NOT IN ('published', 'failed')
                  )
                ORDER BY COALESCE(sg.approved_for_assembly_at, sg.created_at) ASC
                """
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_next_available_slot(existing_slots: list[datetime] = None) -> datetime:
    """
    Find the next available posting slot.
    Returns a datetime in the configured timezone.
    """
    tz = ZoneInfo(config.TIMEZONE)
    now = datetime.now(tz)
    
    # Get existing scheduled times from DB if not provided
    if existing_slots is None:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT scheduled_at FROM scheduled_posts
                    WHERE status IN ('scheduled', 'approved', 'publishing')
                    """
                )
                existing_slots = [r["scheduled_at"] for r in cur.fetchall()]
        finally:
            conn.close()
    
    # Normalize existing slots to the target timezone
    existing_set = set()
    for slot in existing_slots:
        if slot.tzinfo is None:
            slot = slot.replace(tzinfo=ZoneInfo("UTC"))
        existing_set.add(slot.astimezone(tz).replace(second=0, microsecond=0))
    
    # Start from today
    current_date = now.date()
    
    # Search up to 365 days ahead
    for _ in range(365 * 3):  # 3 slots per day * 365 days
        for hour, minute in config.POSTING_TIMES:
            slot_time = time(hour, minute)
            candidate = datetime.combine(current_date, slot_time, tz)
            
            # Skip if in the past (with 5 min buffer)
            if candidate <= now + timedelta(minutes=5):
                continue
            
            # Skip if already scheduled
            candidate_normalized = candidate.replace(second=0, microsecond=0)
            if candidate_normalized in existing_set:
                continue
            
            return candidate
        
        # Move to next day
        current_date += timedelta(days=1)
    
    # Fallback: return tomorrow's first slot
    tomorrow = now.date() + timedelta(days=1)
    first_slot = config.POSTING_TIMES[0]
    return datetime.combine(tomorrow, time(first_slot[0], first_slot[1]), tz)


def add_to_schedule(
    story_generation_id: str,
    assembly_id: str,
    scheduled_at: datetime,
) -> dict:
    """Add a story to the schedule."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Get max position
            cur.execute("SELECT COALESCE(MAX(position), 0) + 1 as next_pos FROM scheduled_posts")
            next_pos = cur.fetchone()["next_pos"]
            
            cur.execute(
                """
                INSERT INTO scheduled_posts (
                    story_generation_id, assembly_id, scheduled_at, position, status
                )
                VALUES (%s, %s, %s, %s, 'scheduled')
                RETURNING id, story_generation_id, assembly_id, scheduled_at, position, 
                          status, created_at, updated_at
                """,
                (story_generation_id, assembly_id, scheduled_at, next_pos),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row)
    except Exception as e:
        conn.rollback()
        logger.error(f"Error adding to schedule: {e}")
        raise
    finally:
        conn.close()


def update_scheduled_post(
    post_id: str,
    *,
    scheduled_at: Optional[datetime] = None,
    position: Optional[int] = None,
    status: Optional[str] = None,
) -> dict | None:
    """Update a scheduled post."""
    if scheduled_at is None and position is None and status is None:
        return get_scheduled_post(post_id)
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            sets = ["updated_at = NOW()"]
            params = []
            
            if scheduled_at is not None:
                sets.append("scheduled_at = %s")
                params.append(scheduled_at)
            if position is not None:
                sets.append("position = %s")
                params.append(position)
            if status is not None:
                sets.append("status = %s")
                params.append(status)
                if status == "approved":
                    sets.append("approved_at = NOW()")
            
            params.append(post_id)
            
            cur.execute(
                f"""
                UPDATE scheduled_posts
                SET {", ".join(sets)}
                WHERE id = %s
                RETURNING *
                """,
                tuple(params),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None
    except Exception as e:
        conn.rollback()
        logger.error(f"Error updating scheduled post: {e}")
        raise
    finally:
        conn.close()


def get_scheduled_post(post_id: str) -> dict | None:
    """Get a single scheduled post by ID."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sp.*, sg.hook_title, sg.subtitle, sg.domain_tag
                FROM scheduled_posts sp
                JOIN story_generations sg ON sp.story_generation_id = sg.id
                WHERE sp.id = %s
                """,
                (post_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def delete_scheduled_post(post_id: str) -> bool:
    """Delete a scheduled post. Returns True if deleted."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM scheduled_posts WHERE id = %s RETURNING id",
                (post_id,),
            )
            row = cur.fetchone()
            conn.commit()
            return row is not None
    except Exception as e:
        conn.rollback()
        logger.error(f"Error deleting scheduled post: {e}")
        raise
    finally:
        conn.close()


def reorder_schedule(post_id: str, new_position: int) -> list[dict]:
    """
    Move a post to a new position and reorder others.
    Returns the updated schedule.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Get current position
            cur.execute(
                "SELECT position FROM scheduled_posts WHERE id = %s",
                (post_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Post {post_id} not found")
            
            old_position = row["position"]
            
            if old_position == new_position:
                return get_scheduled_posts()
            
            # Shift positions
            if new_position < old_position:
                # Moving up: shift others down
                cur.execute(
                    """
                    UPDATE scheduled_posts
                    SET position = position + 1, updated_at = NOW()
                    WHERE position >= %s AND position < %s AND id != %s
                    """,
                    (new_position, old_position, post_id),
                )
            else:
                # Moving down: shift others up
                cur.execute(
                    """
                    UPDATE scheduled_posts
                    SET position = position - 1, updated_at = NOW()
                    WHERE position > %s AND position <= %s AND id != %s
                    """,
                    (old_position, new_position, post_id),
                )
            
            # Set new position
            cur.execute(
                """
                UPDATE scheduled_posts
                SET position = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (new_position, post_id),
            )
            
            conn.commit()
            return get_scheduled_posts()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error reordering schedule: {e}")
        raise
    finally:
        conn.close()


def approve_schedule() -> tuple[int, str]:
    """
    Approve all 'scheduled' posts for auto-posting.
    Returns (count, approval_id).
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Count posts to approve
            cur.execute(
                "SELECT COUNT(*) as cnt FROM scheduled_posts WHERE status = 'scheduled'"
            )
            count = cur.fetchone()["cnt"]
            
            if count == 0:
                return 0, ""
            
            # Update status
            cur.execute(
                """
                UPDATE scheduled_posts
                SET status = 'approved', approved_at = NOW(), updated_at = NOW()
                WHERE status = 'scheduled'
                """
            )
            
            # Create approval record
            cur.execute(
                """
                INSERT INTO schedule_approvals (posts_approved)
                VALUES (%s)
                RETURNING id
                """,
                (count,),
            )
            approval_id = str(cur.fetchone()["id"])
            
            conn.commit()
            return count, approval_id
    except Exception as e:
        conn.rollback()
        logger.error(f"Error approving schedule: {e}")
        raise
    finally:
        conn.close()


# =============================================================================
# Token Queries
# =============================================================================

def get_active_token() -> dict | None:
    """Get the currently active IG access token."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, access_token, token_type, expires_at, obtained_at, 
                       last_used_at, refresh_count, is_active
                FROM ig_access_tokens
                WHERE is_active = TRUE
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def save_new_token(
    access_token: str,
    expires_at: datetime,
    token_type: str = "bearer",
) -> dict:
    """Save a new token and deactivate old ones."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Deactivate all existing tokens
            cur.execute(
                "UPDATE ig_access_tokens SET is_active = FALSE, updated_at = NOW()"
            )
            
            # Insert new token
            cur.execute(
                """
                INSERT INTO ig_access_tokens (access_token, token_type, expires_at, is_active)
                VALUES (%s, %s, %s, TRUE)
                RETURNING id, access_token, token_type, expires_at, obtained_at, is_active
                """,
                (access_token, token_type, expires_at),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row)
    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving token: {e}")
        raise
    finally:
        conn.close()


def update_token_last_used(token_id: str) -> None:
    """Update the last_used_at timestamp for a token."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ig_access_tokens
                SET last_used_at = NOW(), updated_at = NOW()
                WHERE id = %s
                """,
                (token_id,),
            )
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error updating token last_used: {e}")
    finally:
        conn.close()


# =============================================================================
# Assembly Data Queries
# =============================================================================

def get_assembly_for_post(story_generation_id: str) -> dict | None:
    """Get the assembly data for a story."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    sa.id,
                    sa.story_generation_id,
                    sa.assembly_data,
                    sa.status,
                    sg.hook_title,
                    sg.subtitle,
                    sg.instagram_caption,
                    sg.hashtags
                FROM story_assemblies sa
                JOIN story_generations sg ON sa.story_generation_id = sg.id
                WHERE sa.story_generation_id = %s
                ORDER BY sa.updated_at DESC
                LIMIT 1
                """,
                (story_generation_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


# =============================================================================
# Rendered Slides Storage
# =============================================================================

def save_rendered_slides(
    story_generation_id: str,
    rendered_slides: list[dict],
    *,
    assembly_id: str | None = None,
) -> bool:
    """
    Save rendered slide URLs to the assembly_data.
    
    rendered_slides format: [{"index": 0, "filename": "01_cover.png", "public_url": "https://..."}]
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Get assembly data (specific assembly_id if provided, else latest)
            if assembly_id:
                cur.execute(
                    """
                    SELECT id, assembly_data
                    FROM story_assemblies
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (assembly_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT id, assembly_data
                    FROM story_assemblies
                    WHERE story_generation_id = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (story_generation_id,),
                )
            row = cur.fetchone()
            if not row:
                logger.error(f"No assembly found for {story_generation_id} (assembly_id={assembly_id})")
                return False
            
            assembly_id = row["id"]
            assembly_data = row["assembly_data"] or {}
            
            # Add rendered_slides to assembly_data
            assembly_data["rendered_slides"] = rendered_slides
            assembly_data["rendered_at"] = datetime.now().isoformat()
            
            # Update assembly
            cur.execute(
                """
                UPDATE story_assemblies
                SET assembly_data = %s::jsonb, updated_at = NOW()
                WHERE id = %s
                """,
                (json.dumps(assembly_data), assembly_id),
            )
            conn.commit()
            logger.info(f"Saved {len(rendered_slides)} rendered slides for {story_generation_id}")
            return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving rendered slides: {e}")
        return False
    finally:
        conn.close()


def get_posts_needing_render() -> list[dict]:
    """Get approved posts that haven't been rendered yet."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH chosen_assembly AS (
                  SELECT DISTINCT ON (sa.story_generation_id)
                    sa.story_generation_id,
                    sa.id as assembly_id,
                    sa.assembly_data,
                    sa.status,
                    sa.updated_at
                  FROM story_assemblies sa
                  WHERE sa.assembly_data IS NOT NULL
                  ORDER BY
                    sa.story_generation_id,
                    CASE WHEN sa.status = 'finalized' THEN 0 ELSE 1 END,
                    sa.updated_at DESC
                )
                SELECT 
                    sp.id as post_id,
                    sp.story_generation_id,
                    ca.assembly_id,
                    ca.assembly_data
                FROM scheduled_posts sp
                JOIN chosen_assembly ca ON ca.story_generation_id = sp.story_generation_id
                WHERE sp.status = 'approved'
                  AND (
                      ca.assembly_data->'rendered_slides' IS NULL
                      OR jsonb_array_length(ca.assembly_data->'rendered_slides') = 0
                  )
                ORDER BY sp.scheduled_at ASC
                LIMIT 10
                """
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def update_scheduled_post_assembly(*, post_id: str, assembly_id: str) -> None:
    """
    Keep scheduled_posts.assembly_id aligned with the assembly we are rendering/publishing.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scheduled_posts
                SET assembly_id = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (assembly_id, post_id),
            )
            conn.commit()
    finally:
        conn.close()


def update_assembly_data(*, assembly_id: str, assembly_data: dict) -> None:
    """
    Update assembly_data JSON for a specific story_assemblies row.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE story_assemblies
                SET assembly_data = %s::jsonb, updated_at = NOW()
                WHERE id = %s
                """,
                (json.dumps(assembly_data), assembly_id),
            )
            conn.commit()
    finally:
        conn.close()


# =============================================================================
# Health Check
# =============================================================================

def check_db_connection() -> bool:
    """Test database connection."""
    try:
        conn = get_db_connection()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False

