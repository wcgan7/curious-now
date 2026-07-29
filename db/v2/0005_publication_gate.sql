-- Curious Now v2 publication gate.
--
-- A story is published only when its evidence supports the layers it would
-- offer. Stories that never reach sufficient text stay draft: collected,
-- clustered, and available as evidence for stories that do publish, but never
-- shown, because opening a title must lead to an explanation rather than to a
-- dead end pointing elsewhere.

BEGIN;

ALTER TABLE stories
  -- Layers the retrieved text can ground, before generation is considered.
  ADD COLUMN supported_depths TEXT[] NOT NULL DEFAULT '{}',
  ADD COLUMN publication_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN gated_at TIMESTAMPTZ NULL;

-- Ingestion publishes on arrival, which predates this gate. Everything is
-- returned to draft so the gate decides, rather than inheriting a claim made
-- before any text was fetched.
UPDATE stories SET status = 'draft' WHERE status = 'published';

CREATE INDEX idx_stories_gate_pending
  ON stories (last_evidence_at DESC)
  WHERE gated_at IS NULL;

INSERT INTO schema_migrations (version) VALUES ('0005_publication_gate');

COMMIT;
