-- 2026_02_03_0200_stage3_understanding_glossary.sql
-- Stage 3: Understanding layer fields on story_clusters + glossary tables.
-- Matches design_docs/decisions.md and design_docs/stage3_backend.md.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'confidence_band') THEN
    CREATE TYPE confidence_band AS ENUM ('early', 'growing', 'established');
  END IF;
END$$;

-- --- story_clusters: Stage 3 understanding fields ---------------------------
ALTER TABLE story_clusters
  ADD COLUMN IF NOT EXISTS takeaway TEXT NULL,
  ADD COLUMN IF NOT EXISTS takeaway_supporting_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,

  ADD COLUMN IF NOT EXISTS summary_intuition TEXT NULL,
  ADD COLUMN IF NOT EXISTS summary_intuition_supporting_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,

  ADD COLUMN IF NOT EXISTS summary_deep_dive TEXT NULL,
  ADD COLUMN IF NOT EXISTS summary_deep_dive_supporting_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,

  ADD COLUMN IF NOT EXISTS assumptions JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS what_could_change_this JSONB NOT NULL DEFAULT '[]'::jsonb,

  ADD COLUMN IF NOT EXISTS confidence_band confidence_band NULL,
  ADD COLUMN IF NOT EXISTS method_badges JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS anti_hype_flags JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Optional guardrails (soft): ensure arrays are arrays when present
ALTER TABLE story_clusters
  ADD CONSTRAINT story_clusters_takeaway_supporting_item_ids_is_array
  CHECK (jsonb_typeof(takeaway_supporting_item_ids) = 'array')
  NOT VALID;

ALTER TABLE story_clusters
  ADD CONSTRAINT story_clusters_summary_intuition_supporting_item_ids_is_array
  CHECK (jsonb_typeof(summary_intuition_supporting_item_ids) = 'array')
  NOT VALID;

ALTER TABLE story_clusters
  ADD CONSTRAINT story_clusters_summary_deep_dive_supporting_item_ids_is_array
  CHECK (jsonb_typeof(summary_deep_dive_supporting_item_ids) = 'array')
  NOT VALID;

-- --- glossary_entries -------------------------------------------------------
CREATE TABLE IF NOT EXISTS glossary_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  term TEXT NOT NULL,
  definition_short TEXT NOT NULL,
  definition_long TEXT NULL,
  aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
  related_topic_ids JSONB NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT glossary_entries_term_unique UNIQUE (term)
);

CREATE INDEX IF NOT EXISTS idx_glossary_entries_aliases_gin ON glossary_entries USING GIN (aliases);

-- Optional join table to precompute glossary terms that appear in a cluster
CREATE TABLE IF NOT EXISTS cluster_glossary_links (
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  glossary_entry_id UUID NOT NULL REFERENCES glossary_entries(id) ON DELETE CASCADE,
  score DOUBLE PRECISION NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (cluster_id, glossary_entry_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_glossary_links_entry ON cluster_glossary_links (glossary_entry_id, cluster_id);

COMMIT;

