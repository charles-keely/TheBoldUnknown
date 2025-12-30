-- Reset finalized assemblies back to pre-assembly stage.
--
-- What it does:
-- - Finds the latest story_assemblies row per story_generation_id where status='finalized'
-- - Sets that assembly back to status='draft' and clears rendered_files
-- - Sets story_generations.approved_for_assembly=false (prevents the batch assembler from re-finalizing)
--
-- You can run this in Supabase SQL editor.

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



