-- 2026_02_03_0300_stage4_updates_lineage.sql
-- Stage 4: update tracking (cluster revisions + update log) + lineage graph.
-- Matches design_docs/stage4.md and the locked policies in design_docs/decisions.md.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cluster_revision_trigger') THEN
    CREATE TYPE cluster_revision_trigger AS ENUM (
      'new_item',
      'merge',
      'split',
      'quarantine',
      'unquarantine',
      'manual_override',
      'correction'
    );
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cluster_change_type') THEN
    CREATE TYPE cluster_change_type AS ENUM (
      'new_evidence',
      'refinement',
      'contradiction',
      'merge',
      'split',
      'quarantine',
      'unquarantine',
      'correction'
    );
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lineage_node_type') THEN
    CREATE TYPE lineage_node_type AS ENUM ('paper', 'model', 'dataset', 'method');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lineage_relation_type') THEN
    CREATE TYPE lineage_relation_type AS ENUM (
      'extends',
      'improves',
      'compresses',
      'replaces_in_some_settings',
      'contradicts',
      'orthogonal'
    );
  END IF;
END$$;

-- Note: if you already applied an older version of this migration and need to add enum values,
-- add a separate non-transactional migration (many tools require disabling DDL transactions) with:
--   ALTER TYPE cluster_revision_trigger ADD VALUE 'split';
--   ALTER TYPE cluster_revision_trigger ADD VALUE 'quarantine';
--   ALTER TYPE cluster_revision_trigger ADD VALUE 'unquarantine';
--   ALTER TYPE cluster_change_type ADD VALUE 'split';
--   ALTER TYPE cluster_change_type ADD VALUE 'quarantine';
--   ALTER TYPE cluster_change_type ADD VALUE 'unquarantine';

-- --- cluster_revisions ------------------------------------------------------
CREATE TABLE IF NOT EXISTS cluster_revisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  trigger cluster_revision_trigger NOT NULL,

  takeaway TEXT NULL,
  summary_intuition TEXT NULL,
  summary_deep_dive TEXT NULL,
  assumptions JSONB NOT NULL DEFAULT '[]'::jsonb,
  limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
  what_could_change_this JSONB NOT NULL DEFAULT '[]'::jsonb,
  confidence_band confidence_band NULL,
  method_badges JSONB NOT NULL DEFAULT '[]'::jsonb,
  anti_hype_flags JSONB NOT NULL DEFAULT '[]'::jsonb,

  takeaway_supporting_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  summary_intuition_supporting_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  summary_deep_dive_supporting_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,

  evidence_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_cluster_revisions_cluster_created ON cluster_revisions (cluster_id, created_at DESC);

-- --- update_log_entries -----------------------------------------------------
CREATE TABLE IF NOT EXISTS update_log_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  change_type cluster_change_type NOT NULL,

  previous_revision_id UUID NULL REFERENCES cluster_revisions(id) ON DELETE SET NULL,
  new_revision_id UUID NULL REFERENCES cluster_revisions(id) ON DELETE SET NULL,

  summary TEXT NOT NULL,
  diff JSONB NOT NULL DEFAULT '{}'::jsonb,
  supporting_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_update_log_entries_cluster_created ON update_log_entries (cluster_id, created_at DESC);

-- --- lineage graph ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS lineage_nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  node_type lineage_node_type NOT NULL,
  title TEXT NOT NULL,
  external_url TEXT NULL,
  published_at TIMESTAMPTZ NULL,
  external_ids JSONB NULL,
  topic_ids JSONB NULL,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lineage_nodes_node_type ON lineage_nodes (node_type);
CREATE INDEX IF NOT EXISTS idx_lineage_nodes_published_at ON lineage_nodes (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_lineage_nodes_external_ids_gin ON lineage_nodes USING GIN (external_ids);

CREATE TABLE IF NOT EXISTS lineage_edges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_node_id UUID NOT NULL REFERENCES lineage_nodes(id) ON DELETE CASCADE,
  to_node_id UUID NOT NULL REFERENCES lineage_nodes(id) ON DELETE CASCADE,
  relation_type lineage_relation_type NOT NULL,
  evidence_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  notes_short TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lineage_edges_from_to ON lineage_edges (from_node_id, to_node_id);
CREATE INDEX IF NOT EXISTS idx_lineage_edges_relation_type ON lineage_edges (relation_type);

-- Guardrail: forbid edges without evidence (NOT VALID for safer adoption)
ALTER TABLE lineage_edges
  ADD CONSTRAINT lineage_edges_evidence_non_empty
  CHECK (jsonb_typeof(evidence_item_ids) = 'array' AND jsonb_array_length(evidence_item_ids) >= 1)
  NOT VALID;

COMMIT;
