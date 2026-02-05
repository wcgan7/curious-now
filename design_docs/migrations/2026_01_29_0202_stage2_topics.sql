-- 2026_01_29_0202_stage2_topics.sql
-- Stage 2: Topics + cluster_topics join table.
-- Matches the Stage 2 spec in design_docs/stage2.md.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS topics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  description_short TEXT NULL,
  aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
  parent_topic_id UUID NULL REFERENCES topics(id) ON DELETE SET NULL,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_topics_aliases_gin ON topics USING GIN (aliases);

CREATE TABLE IF NOT EXISTS cluster_topics (
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,

  score DOUBLE PRECISION NOT NULL DEFAULT 0,
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (cluster_id, topic_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_topics_topic_cluster ON cluster_topics (topic_id, cluster_id);

COMMIT;

