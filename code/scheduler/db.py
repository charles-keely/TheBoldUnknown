import logging

import psycopg
from psycopg.rows import dict_row

from .config import config

logger = logging.getLogger(__name__)


def get_db_connection_readonly() -> psycopg.Connection:
    """
    Connect to Postgres in a way that prevents accidental writes:
    - default_transaction_read_only=on (server-enforced for the session)
    - statement_timeout to avoid hanging forever
    """
    db_url = config.DATABASE_URL
    if not db_url:
        # Fallback: construct from POSTGRES_* vars (same convention used elsewhere in repo)
        import os

        host = os.getenv("POSTGRES_HOST")
        port = os.getenv("POSTGRES_PORT", "5432")
        dbname = os.getenv("POSTGRES_DB")
        user = os.getenv("POSTGRES_USER")
        password = os.getenv("POSTGRES_PASSWORD")
        if host and dbname and user and password:
            db_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

    if not db_url:
        raise ValueError("DATABASE_URL is not set (and POSTGRES_* fallback was incomplete)")

    # Force readonly at the server side for the session.
    options = f"-c statement_timeout={config.POSTGRES_STATEMENT_TIMEOUT_MS} -c default_transaction_read_only=on"

    conn = psycopg.connect(
        db_url,
        connect_timeout=config.POSTGRES_CONNECT_TIMEOUT,
        options=options,
        row_factory=dict_row,
    )
    return conn


def pick_one_assembly(*, prefer_finalized: bool = True, approved_only: bool = False) -> dict | None:
    """
    Pick one story assembly + caption data.

    Returns:
      {
        story_generation_id,
        hook_title, subtitle, domain_tag,
        instagram_caption, hashtags,
        approved_for_assembly, approved_for_assembly_at,
        assembly_id, assembly_status, assembly_updated_at,
        assembly_data
      }
    """
    conn = get_db_connection_readonly()
    try:
        with conn.cursor() as cur:
            if prefer_finalized:
                cur.execute(
                    """
                    SELECT
                        sg.id as story_generation_id,
                        sg.hook_title,
                        sg.subtitle,
                        sg.domain_tag,
                        sg.instagram_caption,
                        sg.hashtags,
                        COALESCE(sg.approved_for_assembly, FALSE) as approved_for_assembly,
                        sg.approved_for_assembly_at,
                        sa.id as assembly_id,
                        sa.status as assembly_status,
                        sa.updated_at as assembly_updated_at,
                        sa.assembly_data
                    FROM story_generations sg
                    JOIN LATERAL (
                        SELECT sa2.id, sa2.status, sa2.updated_at, sa2.assembly_data
                        FROM story_assemblies sa2
                        WHERE sa2.story_generation_id = sg.id
                        ORDER BY sa2.updated_at DESC
                        LIMIT 1
                    ) sa ON TRUE
                    WHERE COALESCE(sg.is_enabled, TRUE) = TRUE
                      AND (%s = FALSE OR COALESCE(sg.approved_for_assembly, FALSE) = TRUE)
                      AND COALESCE(sa.status, 'draft') = 'finalized'
                      AND sa.assembly_data IS NOT NULL
                    ORDER BY sa.updated_at DESC
                    LIMIT 1
                    """
                    ,
                    (bool(approved_only),),
                )
                row = cur.fetchone()
                if row:
                    return dict(row)

            # Fallback: latest assembly of any status.
            cur.execute(
                """
                SELECT
                    sg.id as story_generation_id,
                    sg.hook_title,
                    sg.subtitle,
                    sg.domain_tag,
                    sg.instagram_caption,
                    sg.hashtags,
                    COALESCE(sg.approved_for_assembly, FALSE) as approved_for_assembly,
                    sg.approved_for_assembly_at,
                    sa.id as assembly_id,
                    sa.status as assembly_status,
                    sa.updated_at as assembly_updated_at,
                    sa.assembly_data
                FROM story_generations sg
                JOIN LATERAL (
                    SELECT sa2.id, sa2.status, sa2.updated_at, sa2.assembly_data
                    FROM story_assemblies sa2
                    WHERE sa2.story_generation_id = sg.id
                    ORDER BY sa2.updated_at DESC
                    LIMIT 1
                ) sa ON TRUE
                WHERE COALESCE(sg.is_enabled, TRUE) = TRUE
                  AND (%s = FALSE OR COALESCE(sg.approved_for_assembly, FALSE) = TRUE)
                  AND sa.assembly_data IS NOT NULL
                ORDER BY
                    COALESCE(sg.approved_for_assembly_at, sa.updated_at) DESC,
                    sa.updated_at DESC
                LIMIT 1
                """,
                (bool(approved_only),),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def pick_assemblies(
    *,
    limit: int = 1,
    prefer_finalized: bool = True,
    approved_only: bool = False,
    exclude_story_generation_ids: list[str] | None = None,
) -> list[dict]:
    """
    Pick multiple story assemblies + caption data.

    Ordering:
    - finalized_first: finalized assemblies first (if prefer_finalized=True), otherwise any
    - newest first by approved_for_assembly_at (fallback: assembly updated_at)
    """
    limit = int(limit)
    if limit <= 0:
        return []
    exclude_story_generation_ids = exclude_story_generation_ids or []

    conn = get_db_connection_readonly()
    try:
        with conn.cursor() as cur:
            params: list = [bool(approved_only), exclude_story_generation_ids, limit]
            if prefer_finalized:
                cur.execute(
                    """
                    WITH latest AS (
                      SELECT DISTINCT ON (sa.story_generation_id)
                        sa.story_generation_id,
                        sa.id as assembly_id,
                        sa.status as assembly_status,
                        sa.updated_at as assembly_updated_at,
                        sa.assembly_data
                      FROM story_assemblies sa
                      WHERE sa.assembly_data IS NOT NULL
                      ORDER BY sa.story_generation_id, sa.updated_at DESC
                    )
                    SELECT
                      sg.id as story_generation_id,
                      sg.hook_title,
                      sg.subtitle,
                      sg.domain_tag,
                      sg.instagram_caption,
                      sg.hashtags,
                      COALESCE(sg.approved_for_assembly, FALSE) as approved_for_assembly,
                      sg.approved_for_assembly_at,
                      l.assembly_id,
                      l.assembly_status,
                      l.assembly_updated_at,
                      l.assembly_data
                    FROM story_generations sg
                    JOIN latest l ON l.story_generation_id = sg.id
                    WHERE COALESCE(sg.is_enabled, TRUE) = TRUE
                      AND (%s = FALSE OR COALESCE(sg.approved_for_assembly, FALSE) = TRUE)
                      AND (cardinality(%s::uuid[]) = 0 OR sg.id <> ALL(%s::uuid[]))
                    ORDER BY
                      CASE WHEN COALESCE(l.assembly_status, 'draft') = 'finalized' THEN 0 ELSE 1 END,
                      COALESCE(sg.approved_for_assembly_at, l.assembly_updated_at) DESC,
                      l.assembly_updated_at DESC
                    LIMIT %s
                    """,
                    (params[0], params[1], params[1], params[2]),
                )
            else:
                cur.execute(
                    """
                    WITH latest AS (
                      SELECT DISTINCT ON (sa.story_generation_id)
                        sa.story_generation_id,
                        sa.id as assembly_id,
                        sa.status as assembly_status,
                        sa.updated_at as assembly_updated_at,
                        sa.assembly_data
                      FROM story_assemblies sa
                      WHERE sa.assembly_data IS NOT NULL
                      ORDER BY sa.story_generation_id, sa.updated_at DESC
                    )
                    SELECT
                      sg.id as story_generation_id,
                      sg.hook_title,
                      sg.subtitle,
                      sg.domain_tag,
                      sg.instagram_caption,
                      sg.hashtags,
                      COALESCE(sg.approved_for_assembly, FALSE) as approved_for_assembly,
                      sg.approved_for_assembly_at,
                      l.assembly_id,
                      l.assembly_status,
                      l.assembly_updated_at,
                      l.assembly_data
                    FROM story_generations sg
                    JOIN latest l ON l.story_generation_id = sg.id
                    WHERE COALESCE(sg.is_enabled, TRUE) = TRUE
                      AND (%s = FALSE OR COALESCE(sg.approved_for_assembly, FALSE) = TRUE)
                      AND (cardinality(%s::uuid[]) = 0 OR sg.id <> ALL(%s::uuid[]))
                    ORDER BY
                      COALESCE(sg.approved_for_assembly_at, l.assembly_updated_at) DESC,
                      l.assembly_updated_at DESC
                    LIMIT %s
                    """,
                    (params[0], params[1], params[1], params[2]),
                )
            rows = cur.fetchall() or []
            return [dict(r) for r in rows]
    finally:
        conn.close()


def get_thumbnail_source(*, thumbnail_id: str) -> dict | None:
    """
    Fetch thumbnail source data for rendering cover slides.

    We support:
    - story_thumbnails.image_url (preferred if it's a public URL)
    - story_thumbnails.generation_metadata.image_base64 (fallback; used by Pre-Assembler endpoint)

    Returns:
      { "image_url": str|None, "image_base64": str|None, "mime_type": str|None }
    """
    conn = get_db_connection_readonly()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT image_url, generation_metadata
                FROM story_thumbnails
                WHERE id = %s
                """,
                (thumbnail_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            gm = row.get("generation_metadata") or {}
            if not isinstance(gm, dict):
                gm = {}
            return {
                "image_url": row.get("image_url"),
                "image_base64": gm.get("image_base64"),
                "mime_type": gm.get("mime_type") or "image/png",
            }
    finally:
        conn.close()


