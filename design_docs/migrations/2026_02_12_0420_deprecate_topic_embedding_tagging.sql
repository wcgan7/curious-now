-- 2026_02_12_0420_deprecate_topic_embedding_tagging.sql
-- Deprecate embedding-based topic tagging artifacts.
--
-- Notes:
-- - Keep enum value `embedding` in topic_assignment_source for migration compatibility.
-- - Runtime topic tagging is now LLM-only.

BEGIN;

-- Normalize historical embedding assignments to llm provenance.
UPDATE cluster_topics
SET assignment_source = 'llm'
WHERE assignment_source = 'embedding';

-- Drop unused topic-embedding storage and related trigger/index.
DROP TRIGGER IF EXISTS trg_topic_embeddings_set_updated_at ON topic_embeddings;
DROP TABLE IF EXISTS topic_embeddings;

COMMIT;
