-- 2026_02_10_0300_stage3_high_impact.sql
-- Stage 3/4: high-impact paper scoring and calibrated top-1% labeling fields.

BEGIN;

ALTER TABLE story_clusters
  ADD COLUMN IF NOT EXISTS high_impact_provisional_score DOUBLE PRECISION NULL,
  ADD COLUMN IF NOT EXISTS high_impact_final_score DOUBLE PRECISION NULL,
  ADD COLUMN IF NOT EXISTS high_impact_confidence DOUBLE PRECISION NULL,
  ADD COLUMN IF NOT EXISTS high_impact_label BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS high_impact_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS high_impact_version TEXT NULL,
  ADD COLUMN IF NOT EXISTS high_impact_assessed_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS high_impact_eligible BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS high_impact_threshold_bucket TEXT NULL,
  ADD COLUMN IF NOT EXISTS high_impact_threshold_value DOUBLE PRECISION NULL;

ALTER TABLE story_clusters
  ADD CONSTRAINT story_clusters_high_impact_reasons_is_array
  CHECK (jsonb_typeof(high_impact_reasons) = 'array')
  NOT VALID;

CREATE INDEX IF NOT EXISTS idx_story_clusters_high_impact_label_updated
  ON story_clusters (updated_at DESC)
  WHERE status = 'active' AND high_impact_label = TRUE;

CREATE INDEX IF NOT EXISTS idx_story_clusters_high_impact_assessed_at
  ON story_clusters (high_impact_assessed_at DESC)
  WHERE high_impact_assessed_at IS NOT NULL;

COMMIT;
