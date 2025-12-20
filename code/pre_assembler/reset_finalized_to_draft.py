"""
Reset finalized assemblies back to pre-assembly stage.

What it does:
- Finds the *latest* assembly row per story_generation_id where latest status == 'finalized'
- Updates that assembly to status='draft' and clears rendered_files
- Sets story_generations.approved_for_assembly=false (and clears approved_for_assembly_at)

Why:
Pre-Assembler hides stories whose latest assembly is finalized. If you discover
critical issues after posting, this script re-opens everything for review.

Safety:
- Supports --dry-run to only print counts
- Uses a single transaction
"""

import argparse
import logging

try:
    # package-style
    from pre_assembler.db import get_db_connection
except ImportError:
    # local-folder style (when running from within pre_assembler/)
    from db import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("pre_assembler.reset_finalized")


RESET_SQL = """
WITH latest AS (
  SELECT sa.id, sa.story_generation_id
  FROM story_assemblies sa
  JOIN (
    SELECT story_generation_id, MAX(updated_at) AS max_updated_at
    FROM story_assemblies
    GROUP BY story_generation_id
  ) m
    ON m.story_generation_id = sa.story_generation_id
   AND m.max_updated_at = sa.updated_at
  WHERE sa.status = 'finalized'
),
upd_assemblies AS (
  UPDATE story_assemblies sa
  SET status = 'draft',
      rendered_files = NULL,
      updated_at = NOW()
  FROM latest l
  WHERE sa.id = l.id
  RETURNING sa.id, sa.story_generation_id
),
upd_generations AS (
  UPDATE story_generations sg
  SET approved_for_assembly = FALSE,
      approved_for_assembly_at = NULL
  WHERE sg.id IN (SELECT story_generation_id FROM latest)
  RETURNING sg.id
)
SELECT
  (SELECT COUNT(*) FROM latest) AS latest_finalized_count,
  (SELECT COUNT(*) FROM upd_assemblies) AS assemblies_reset_count,
  (SELECT COUNT(*) FROM upd_generations) AS generations_unapproved_count
;
"""


COUNT_ONLY_SQL = """
WITH latest AS (
  SELECT sa.id, sa.story_generation_id
  FROM story_assemblies sa
  JOIN (
    SELECT story_generation_id, MAX(updated_at) AS max_updated_at
    FROM story_assemblies
    GROUP BY story_generation_id
  ) m
    ON m.story_generation_id = sa.story_generation_id
   AND m.max_updated_at = sa.updated_at
  WHERE sa.status = 'finalized'
)
SELECT COUNT(*) AS latest_finalized_count
FROM latest;
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Reset finalized assemblies back to draft for Pre-Assembler review.")
    ap.add_argument("--dry-run", action="store_true", help="Only print how many stories would be reset.")
    args = ap.parse_args()

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if args.dry_run:
                cur.execute(COUNT_ONLY_SQL)
                row = cur.fetchone() or {}
                logger.info(f"Would reset {row.get('latest_finalized_count', 0)} stories (latest assembly is finalized).")
                conn.rollback()
                return 0

            cur.execute(RESET_SQL)
            row = cur.fetchone() or {}
            conn.commit()
            logger.info(
                "Reset complete: "
                f"latest_finalized={row.get('latest_finalized_count', 0)} "
                f"assemblies_reset={row.get('assemblies_reset_count', 0)} "
                f"generations_unapproved={row.get('generations_unapproved_count', 0)}"
            )
            return 0
    except Exception as e:
        conn.rollback()
        logger.error(f"Reset failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())


