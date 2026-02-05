-- 2026_02_03_0900_stage10_entities_experiments.sql
-- Stage 10: entity system + knowledge graph edges + experiments + feature flags.
-- Matches design_docs/stage10.md.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'entity_type') THEN
    CREATE TYPE entity_type AS ENUM ('person', 'institution', 'model', 'dataset', 'method', 'venue');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'entity_relation_type') THEN
    CREATE TYPE entity_relation_type AS ENUM (
      'authored_by',
      'affiliated_with',
      'trained_on',
      'uses_method',
      'uses_dataset',
      'published_in',
      'maintained_by',
      'introduced'
    );
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'entity_redirect_type') THEN
    CREATE TYPE entity_redirect_type AS ENUM ('merge');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'entity_assignment_source') THEN
    CREATE TYPE entity_assignment_source AS ENUM ('auto', 'editor');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'experiment_subject_type') THEN
    CREATE TYPE experiment_subject_type AS ENUM ('user', 'client');
  END IF;
END$$;

-- --- entities --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type entity_type NOT NULL,
  name TEXT NOT NULL,
  description_short TEXT NULL,
  external_url TEXT NULL,
  external_ids JSONB NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT entities_type_name_unique UNIQUE (entity_type, name)
);

CREATE INDEX IF NOT EXISTS idx_entities_type_name ON entities (entity_type, name);
CREATE INDEX IF NOT EXISTS idx_entities_external_ids_gin ON entities USING GIN (external_ids);

DROP TRIGGER IF EXISTS trg_entities_set_updated_at ON entities;
CREATE TRIGGER trg_entities_set_updated_at
BEFORE UPDATE ON entities
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- --- entity_aliases ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_aliases (
  entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (entity_id, alias)
);

CREATE INDEX IF NOT EXISTS idx_entity_aliases_alias ON entity_aliases (alias);

-- --- entity_redirects -------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_redirects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  to_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  redirect_type entity_redirect_type NOT NULL DEFAULT 'merge',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT entity_redirects_from_unique UNIQUE (from_entity_id),
  CONSTRAINT entity_redirects_not_self CHECK (from_entity_id <> to_entity_id)
);

CREATE INDEX IF NOT EXISTS idx_entity_redirects_to ON entity_redirects (to_entity_id);

-- --- cluster_entities -------------------------------------------------------
CREATE TABLE IF NOT EXISTS cluster_entities (
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  score DOUBLE PRECISION NOT NULL DEFAULT 0,
  assignment_source entity_assignment_source NOT NULL DEFAULT 'auto',
  locked BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (cluster_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_entities_entity_cluster ON cluster_entities (entity_id, cluster_id);

-- --- entity_edges -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_edges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  to_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  relation_type entity_relation_type NOT NULL,
  evidence_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  notes_short TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_entity_edges_from_to ON entity_edges (from_entity_id, to_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_edges_relation_type ON entity_edges (relation_type);

ALTER TABLE entity_edges
  ADD CONSTRAINT entity_edges_evidence_non_empty
  CHECK (jsonb_typeof(evidence_item_ids) = 'array' AND jsonb_array_length(evidence_item_ids) >= 1)
  NOT VALID;

-- --- user_entity_follows ----------------------------------------------------
CREATE TABLE IF NOT EXISTS user_entity_follows (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_user_entity_follows_entity_user ON user_entity_follows (entity_id, user_id);

-- --- experiments + assignments ---------------------------------------------
CREATE TABLE IF NOT EXISTS experiments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key TEXT NOT NULL UNIQUE,
  description TEXT NULL,
  active BOOLEAN NOT NULL DEFAULT false,
  start_at TIMESTAMPTZ NULL,
  end_at TIMESTAMPTZ NULL,
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_experiments_set_updated_at ON experiments;
CREATE TRIGGER trg_experiments_set_updated_at
BEFORE UPDATE ON experiments
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS experiment_variants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT experiment_variants_unique UNIQUE (experiment_id, key)
);

CREATE INDEX IF NOT EXISTS idx_experiment_variants_experiment ON experiment_variants (experiment_id, weight DESC);

CREATE TABLE IF NOT EXISTS experiment_assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_type experiment_subject_type NOT NULL,
  subject_id UUID NOT NULL,
  experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  variant_id UUID NOT NULL REFERENCES experiment_variants(id) ON DELETE CASCADE,
  assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT experiment_assignments_subject_unique UNIQUE (subject_type, subject_id, experiment_id)
);

CREATE INDEX IF NOT EXISTS idx_experiment_assignments_experiment_variant ON experiment_assignments (experiment_id, variant_id);
CREATE INDEX IF NOT EXISTS idx_experiment_assignments_subject ON experiment_assignments (subject_type, subject_id, assigned_at DESC);

-- --- feature_flags ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS feature_flags (
  key TEXT PRIMARY KEY,
  enabled BOOLEAN NOT NULL DEFAULT false,
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_feature_flags_set_updated_at ON feature_flags;
CREATE TRIGGER trg_feature_flags_set_updated_at
BEFORE UPDATE ON feature_flags
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;

