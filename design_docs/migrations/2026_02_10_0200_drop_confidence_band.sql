-- 2026_02_10_0200_drop_confidence_band.sql
-- Cleanup: remove deprecated confidence-band schema artifacts.

BEGIN;

ALTER TABLE IF EXISTS story_clusters
  DROP COLUMN IF EXISTS confidence_band;

ALTER TABLE IF EXISTS cluster_revisions
  DROP COLUMN IF EXISTS confidence_band;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'confidence_band')
     AND NOT EXISTS (
       SELECT 1
       FROM information_schema.columns
       WHERE udt_name = 'confidence_band'
     ) THEN
    DROP TYPE confidence_band;
  END IF;
END$$;

COMMIT;
