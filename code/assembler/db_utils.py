"""
Database helpers for the batch Assembler.

The assembler:
- Pulls the latest non-finalized assembly for stories approved_for_assembly
- Marks an assembly as finalized after rendering completes
"""

import os
import json
import logging
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables (.env in assembler/ or repo root, plus process env)
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
load_dotenv(os.path.join(current_dir, ".env"))
load_dotenv(os.path.join(root_dir, ".env"))
load_dotenv()


def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    connect_timeout = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))  # seconds
    statement_timeout_ms = int(os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS", "15000"))

    # Fallback: construct from POSTGRES_* vars
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

    return psycopg.connect(
        db_url,
        connect_timeout=connect_timeout,
        options=f"-c statement_timeout={statement_timeout_ms}",
        row_factory=dict_row,
    )


def get_pending_assemblies():
    """
    Return the latest assembly row (assembly_data) for each story_generation_id where:
    - story_generations.approved_for_assembly = true
    - story_assemblies.status != 'finalized'
    - story_generations.is_enabled = true (default true)
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    sg.id as story_generation_id,
                    sg.hook_title,
                    sg.subtitle,
                    sg.domain_tag,
                    sa.id as assembly_id,
                    sa.assembly_data,
                    sa.status as assembly_status,
                    sa.updated_at as assembly_updated_at
                FROM story_generations sg
                JOIN LATERAL (
                    SELECT sa2.id, sa2.assembly_data, sa2.status, sa2.updated_at
                    FROM story_assemblies sa2
                    WHERE sa2.story_generation_id = sg.id
                    ORDER BY sa2.updated_at DESC
                    LIMIT 1
                ) sa ON TRUE
                WHERE COALESCE(sg.is_enabled, TRUE) = TRUE
                  AND COALESCE(sg.approved_for_assembly, FALSE) = TRUE
                  AND COALESCE(sa.status, 'draft') != 'finalized'
                ORDER BY sa.updated_at ASC
                """
            )
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching pending assemblies: {e}")
        return []
    finally:
        conn.close()


def mark_assembly_finalized(story_generation_id: str, rendered_files):
    """
    Mark the latest assembly for story_generation_id as finalized and store rendered_files.

    rendered_files should be JSON-serializable. (e.g., list of filenames, or list of paths)
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Update the most recent assembly row for this story.
            cur.execute(
                """
                UPDATE story_assemblies
                SET status = 'finalized',
                    rendered_files = %s::jsonb,
                    updated_at = NOW()
                WHERE id = (
                    SELECT id
                    FROM story_assemblies
                    WHERE story_generation_id = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                )
                """,
                (json.dumps(rendered_files), story_generation_id),
            )
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error finalizing assembly for {story_generation_id}: {e}")
        raise
    finally:
        conn.close()


