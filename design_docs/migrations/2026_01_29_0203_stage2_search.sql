-- 2026_01_29_0203_stage2_search.sql
-- Stage 2: cluster-first keyword search via Postgres full-text search.
-- Matches the Stage 2 spec in design_docs/stage2.md.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS cluster_search_docs (
  cluster_id UUID PRIMARY KEY REFERENCES story_clusters(id) ON DELETE CASCADE,

  -- worker-controlled text blob:
  -- canonical title + top N item titles + optional identifiers (arxiv_id/doi)
  search_text TEXT NOT NULL DEFAULT '',

  search_tsv TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(search_text, ''))
  ) STORED,

  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cluster_search_docs_tsv ON cluster_search_docs USING GIN (search_tsv);
CREATE INDEX IF NOT EXISTS idx_cluster_search_docs_updated_at ON cluster_search_docs (updated_at DESC);

COMMIT;

