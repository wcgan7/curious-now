-- 2026_02_03_0600_stage7_vector_search_pgvector.sql
-- Stage 7 (optional): pgvector tables for semantic search / clustering support.
-- Matches design_docs/stage7.md.
--
-- Prereq: pgvector must be installed on your Postgres (extension name: "vector").

BEGIN;

-- Enable pgvector (will fail if pgvector is not installed on the server)
CREATE EXTENSION IF NOT EXISTS vector;

-- Default dimension: 1536 (matches common embedding models; adjust only with a deliberate migration).
CREATE TABLE IF NOT EXISTS cluster_embeddings (
  cluster_id UUID PRIMARY KEY REFERENCES story_clusters(id) ON DELETE CASCADE,
  embedding vector(1536) NOT NULL,
  embedding_model TEXT NOT NULL DEFAULT 'default',
  source_text_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cluster_embeddings_embedding_ivfflat
  ON cluster_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

DROP TRIGGER IF EXISTS trg_cluster_embeddings_set_updated_at ON cluster_embeddings;
CREATE TRIGGER trg_cluster_embeddings_set_updated_at
BEFORE UPDATE ON cluster_embeddings
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;

