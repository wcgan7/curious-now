-- 2026_02_12_0400_topic_embeddings.sql
-- Topic embeddings for embedding-based topic tagging.
-- Superseded by 2026_02_12_0420_deprecate_topic_embedding_tagging.sql.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS topic_embeddings (
  topic_id UUID PRIMARY KEY REFERENCES topics(id) ON DELETE CASCADE,
  embedding vector(1536) NOT NULL,
  embedding_model TEXT NOT NULL DEFAULT 'default',
  source_text_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_topic_embeddings_embedding_ivfflat
  ON topic_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

DROP TRIGGER IF EXISTS trg_topic_embeddings_set_updated_at ON topic_embeddings;
CREATE TRIGGER trg_topic_embeddings_set_updated_at
BEFORE UPDATE ON topic_embeddings
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
