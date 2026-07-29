-- Curious Now v2 presentation model.
--
-- Separates the internal working title from versioned reader-facing display
-- titles, records the conceptual spine each presentation renders from, and
-- keys explanations to one evidence-packet version plus one spine version.

BEGIN;

ALTER TABLE stories RENAME COLUMN canonical_title TO working_title;

CREATE TABLE conceptual_spines (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  evidence_packet_id UUID NOT NULL REFERENCES evidence_packets(id) ON DELETE CASCADE,
  version INTEGER NOT NULL CHECK (version > 0),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (
    status IN ('draft', 'valid', 'invalid', 'superseded')
  ),
  central_claim TEXT NOT NULL,
  novelty TEXT NULL,
  core_intuition TEXT NULL,
  why_it_matters JSONB NOT NULL DEFAULT '[]'::jsonb,
  strongest_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
  essential_qualification TEXT NULL,
  prerequisite_concepts JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_roles JSONB NOT NULL DEFAULT '{}'::jsonb,
  prompt_version TEXT NOT NULL,
  model_provider TEXT NULL,
  model_name TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at TIMESTAMPTZ NULL,
  UNIQUE (evidence_packet_id, version)
);

CREATE INDEX idx_conceptual_spines_story
  ON conceptual_spines (story_id, created_at DESC);

CREATE TABLE display_titles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  evidence_packet_id UUID NOT NULL REFERENCES evidence_packets(id) ON DELETE CASCADE,
  conceptual_spine_id UUID NULL REFERENCES conceptual_spines(id) ON DELETE SET NULL,
  version INTEGER NOT NULL CHECK (version > 0),
  text TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (
    status IN ('pending', 'valid', 'invalid', 'failed', 'superseded')
  ),
  prompt_version TEXT NOT NULL,
  model_provider TEXT NULL,
  model_name TEXT NULL,
  failure_reason TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at TIMESTAMPTZ NULL,
  UNIQUE (story_id, version)
);

CREATE INDEX idx_display_titles_story
  ON display_titles (story_id, version DESC);

ALTER TABLE stories
  ADD COLUMN current_display_title_id UUID NULL
  REFERENCES display_titles(id);

ALTER TABLE explanations
  ADD COLUMN conceptual_spine_id UUID NULL
  REFERENCES conceptual_spines(id);

-- NULLS NOT DISTINCT so pre-spine explanations cannot silently duplicate.
ALTER TABLE explanations
  DROP CONSTRAINT explanations_evidence_packet_id_depth_prompt_version_key;

ALTER TABLE explanations
  ADD CONSTRAINT explanations_packet_spine_depth_prompt_key
  UNIQUE NULLS NOT DISTINCT (
    evidence_packet_id,
    conceptual_spine_id,
    depth,
    prompt_version
  );

INSERT INTO schema_migrations (version) VALUES ('0002_presentation_model');

COMMIT;
