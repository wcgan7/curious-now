-- 2026_01_29_0201_stage2_clusters.sql
-- Stage 2: StoryClusters + ClusterItems + assignment logs + external IDs on items.
-- Matches the Stage 2 spec in design_docs/stage2.md.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cluster_status') THEN
    CREATE TYPE cluster_status AS ENUM ('active', 'merged', 'quarantined');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cluster_item_role') THEN
    CREATE TYPE cluster_item_role AS ENUM ('primary', 'supporting', 'background');
  END IF;
END$$;

-- Ensure external ID columns exist (Stage 1 migration also creates these; keep for safety).
ALTER TABLE items
  ADD COLUMN IF NOT EXISTS arxiv_id TEXT,
  ADD COLUMN IF NOT EXISTS doi TEXT,
  ADD COLUMN IF NOT EXISTS pmid TEXT,
  ADD COLUMN IF NOT EXISTS external_ids JSONB;

CREATE INDEX IF NOT EXISTS idx_items_arxiv_id ON items (arxiv_id) WHERE arxiv_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_doi ON items (doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_pmid ON items (pmid) WHERE pmid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_external_ids_gin ON items USING GIN (external_ids);

CREATE TABLE IF NOT EXISTS story_clusters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status cluster_status NOT NULL DEFAULT 'active',

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  canonical_title TEXT NOT NULL,
  representative_item_id UUID NULL REFERENCES items(id) ON DELETE SET NULL,

  distinct_source_count INT NOT NULL DEFAULT 0,
  distinct_source_type_count INT NOT NULL DEFAULT 0,
  item_count INT NOT NULL DEFAULT 0,

  velocity_6h INT NOT NULL DEFAULT 0,
  velocity_24h INT NOT NULL DEFAULT 0,

  trending_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  recency_score DOUBLE PRECISION NOT NULL DEFAULT 0,

  metrics_extra JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_story_clusters_updated_at ON story_clusters (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_story_clusters_trending_score ON story_clusters (trending_score DESC);

CREATE TABLE IF NOT EXISTS cluster_items (
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,

  role cluster_item_role NOT NULL DEFAULT 'supporting',
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (cluster_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_items_item_id ON cluster_items (item_id);
CREATE INDEX IF NOT EXISTS idx_cluster_items_cluster_added_at ON cluster_items (cluster_id, added_at DESC);

CREATE TABLE IF NOT EXISTS cluster_assignment_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  decided_cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,

  decision TEXT NOT NULL CHECK (decision IN ('created_new', 'attached_existing', 'merged_clusters')),

  candidate_cluster_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  score_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
  threshold_used DOUBLE PRECISION NULL
);

CREATE INDEX IF NOT EXISTS idx_cluster_assignment_logs_created_at ON cluster_assignment_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cluster_assignment_logs_item_id ON cluster_assignment_logs (item_id);

COMMIT;

