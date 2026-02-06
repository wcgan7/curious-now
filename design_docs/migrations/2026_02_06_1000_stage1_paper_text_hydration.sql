-- 2026_02_06_1000_stage1_paper_text_hydration.sql
-- Add paper text hydration fields for preprint/peer_reviewed quality.

BEGIN;

ALTER TABLE items
  ADD COLUMN IF NOT EXISTS full_text TEXT NULL,
  ADD COLUMN IF NOT EXISTS full_text_status TEXT NULL,
  ADD COLUMN IF NOT EXISTS full_text_source TEXT NULL,
  ADD COLUMN IF NOT EXISTS full_text_fetched_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS full_text_error TEXT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'items_full_text_status_check'
  ) THEN
    ALTER TABLE items
      ADD CONSTRAINT items_full_text_status_check
      CHECK (
        full_text_status IS NULL
        OR full_text_status IN ('pending', 'ok', 'not_found', 'paywalled', 'error')
      );
  END IF;
END$$;

-- Backfill status for existing paper rows that still have no hydrated text.
UPDATE items
SET full_text_status = 'pending'
WHERE content_type IN ('preprint', 'peer_reviewed')
  AND (full_text IS NULL OR btrim(full_text) = '')
  AND full_text_status IS NULL;

CREATE INDEX IF NOT EXISTS idx_items_paper_text_pending
  ON items (content_type, full_text_status, fetched_at DESC)
  WHERE content_type IN ('preprint', 'peer_reviewed');

COMMIT;
