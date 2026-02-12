-- 2026_02_11_0100_stage3_high_impact_debug.sql
-- Add debug payload for deterministic high-impact calibration analysis.

BEGIN;

ALTER TABLE story_clusters
  ADD COLUMN IF NOT EXISTS high_impact_debug JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE story_clusters
  ADD CONSTRAINT story_clusters_high_impact_debug_is_object
  CHECK (jsonb_typeof(high_impact_debug) = 'object')
  NOT VALID;

COMMIT;
