-- Stage 3: debug visibility for deep-dive generation gating
ALTER TABLE story_clusters
  ADD COLUMN IF NOT EXISTS deep_dive_skip_reason TEXT NULL;

