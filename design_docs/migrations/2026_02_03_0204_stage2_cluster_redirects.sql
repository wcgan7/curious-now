-- 2026_02_03_0204_stage2_cluster_redirects.sql
-- Stage 2: cluster redirects to make merges safe for stable URLs/bookmarks.
-- This migration is intentionally small and can be applied any time after story_clusters exists.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cluster_redirect_type') THEN
    CREATE TYPE cluster_redirect_type AS ENUM ('merge');
  END IF;
END$$;

CREATE TABLE IF NOT EXISTS cluster_redirects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  to_cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  redirect_type cluster_redirect_type NOT NULL DEFAULT 'merge',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT cluster_redirects_from_unique UNIQUE (from_cluster_id),
  CONSTRAINT cluster_redirects_not_self CHECK (from_cluster_id <> to_cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_redirects_to ON cluster_redirects (to_cluster_id);

COMMIT;

