-- 2026_02_12_0410_topic_assignment_source_embedding.sql
-- Extend topic assignment source enum for embedding + llm provenance.
-- `embedding` provenance is deprecated by 2026_02_12_0420_deprecate_topic_embedding_tagging.sql.

BEGIN;

DO $$
BEGIN
  ALTER TYPE topic_assignment_source ADD VALUE IF NOT EXISTS 'embedding';
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  ALTER TYPE topic_assignment_source ADD VALUE IF NOT EXISTS 'llm';
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

COMMIT;
