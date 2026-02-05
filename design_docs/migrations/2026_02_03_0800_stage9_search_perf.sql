-- 2026_02_03_0800_stage9_search_perf.sql
-- Stage 9: performance + search/ranking support indexes.
-- Matches design_docs/stage9.md.

BEGIN;

-- Feed queries almost always want active clusters; partial indexes help at scale.
CREATE INDEX IF NOT EXISTS idx_story_clusters_active_updated_at
  ON story_clusters (updated_at DESC)
  WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_story_clusters_active_trending_score
  ON story_clusters (trending_score DESC)
  WHERE status = 'active';

-- Optional but recommended for fuzzy matching / typo tolerance.
-- Best-effort: if pg_trgm is unavailable (or extension/index privileges are missing), skip trigram support.
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS pg_trgm;

  CREATE INDEX IF NOT EXISTS idx_cluster_search_docs_search_text_trgm
    ON cluster_search_docs USING GIN (search_text gin_trgm_ops);

  CREATE INDEX IF NOT EXISTS idx_topics_name_trgm
    ON topics USING GIN (name gin_trgm_ops);
EXCEPTION
  WHEN OTHERS THEN
    RAISE NOTICE 'Skipping pg_trgm extension and trigram indexes: %', SQLERRM;
END $$;

COMMIT;
