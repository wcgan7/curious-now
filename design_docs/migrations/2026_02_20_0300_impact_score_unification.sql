-- 2026_02_20_0300_impact_score_unification.sql
-- Stage: unify ranking on impact_score and add in-focus badge label.

ALTER TABLE story_clusters
  ADD COLUMN IF NOT EXISTS impact_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS in_focus_label BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS impact_assessed_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS impact_debug JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_story_clusters_active_impact_score
  ON story_clusters (impact_score DESC)
  WHERE status = 'active';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_story_clusters_active_in_focus_updated
  ON story_clusters (updated_at DESC)
  WHERE status = 'active' AND in_focus_label = TRUE;
