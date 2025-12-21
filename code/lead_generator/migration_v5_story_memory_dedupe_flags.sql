-- story_memory: allow muting entries from dedupe (e.g., leads removed from posting)

ALTER TABLE public.story_memory
  ADD COLUMN IF NOT EXISTS is_active_for_dedupe boolean NOT NULL DEFAULT true;

CREATE INDEX IF NOT EXISTS idx_story_memory_is_active_for_dedupe
  ON public.story_memory(is_active_for_dedupe);

-- Auto-mute lead-based memory if the lead is deleted or rejected.
-- NOTE: We only mute source_type='lead' rows. Published/assembled memory remains.

CREATE OR REPLACE FUNCTION public.story_memory_mute_on_lead_delete()
RETURNS trigger AS $$
BEGIN
  UPDATE public.story_memory
  SET is_active_for_dedupe = FALSE,
      updated_at = now()
  WHERE source_type = 'lead'
    AND source_id = OLD.id;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_story_memory_mute_on_lead_delete ON public.leads;
CREATE TRIGGER trg_story_memory_mute_on_lead_delete
AFTER DELETE ON public.leads
FOR EACH ROW
EXECUTE FUNCTION public.story_memory_mute_on_lead_delete();

CREATE OR REPLACE FUNCTION public.story_memory_mute_on_lead_reject()
RETURNS trigger AS $$
BEGIN
  IF NEW.status = 'rejected' THEN
    UPDATE public.story_memory
    SET is_active_for_dedupe = FALSE,
        updated_at = now()
    WHERE source_type = 'lead'
      AND source_id = NEW.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_story_memory_mute_on_lead_reject ON public.leads;
CREATE TRIGGER trg_story_memory_mute_on_lead_reject
AFTER UPDATE OF status ON public.leads
FOR EACH ROW
EXECUTE FUNCTION public.story_memory_mute_on_lead_reject();


