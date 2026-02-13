-- 2026_02_03_0700_stage8_governance_editorial.sql
-- Stage 8: governance + editorial tooling (feedback, audit log, topic redirects, manual topic locks).
-- Matches design_docs/stage8.md.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'feedback_type') THEN
    CREATE TYPE feedback_type AS ENUM (
      'confusing',
      'overstated',
      'incorrect',
      'missing_context',
      'broken_link',
      'other'
    );
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'feedback_status') THEN
    CREATE TYPE feedback_status AS ENUM ('new', 'triaged', 'resolved', 'ignored');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'editor_actor_type') THEN
    CREATE TYPE editor_actor_type AS ENUM ('admin_token', 'user_session', 'system');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'editorial_action_type') THEN
    CREATE TYPE editorial_action_type AS ENUM (
      'merge_cluster',
      'split_cluster',
      'quarantine_cluster',
      'unquarantine_cluster',
      'override_cluster',
      'correct_cluster',
      'set_cluster_topics',
      'create_topic',
      'rename_topic',
      'merge_topic',
      'create_lineage_node',
      'create_lineage_edge',
      'update_lineage_edge',
      'delete_lineage_edge',
      'audit_source',
      'resolve_feedback'
    );
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'topic_redirect_type') THEN
    CREATE TYPE topic_redirect_type AS ENUM ('merge');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'topic_assignment_source') THEN
    CREATE TYPE topic_assignment_source AS ENUM ('auto', 'editor');
  END IF;
END$$;

-- --- topic_redirects --------------------------------------------------------
CREATE TABLE IF NOT EXISTS topic_redirects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  to_topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  redirect_type topic_redirect_type NOT NULL DEFAULT 'merge',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT topic_redirects_from_unique UNIQUE (from_topic_id),
  CONSTRAINT topic_redirects_not_self CHECK (from_topic_id <> to_topic_id)
);

CREATE INDEX IF NOT EXISTS idx_topic_redirects_to ON topic_redirects (to_topic_id);

-- --- feedback_reports -------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  user_id UUID NULL,
  client_id UUID NULL,

  cluster_id UUID NULL REFERENCES story_clusters(id) ON DELETE SET NULL,
  item_id UUID NULL REFERENCES items(id) ON DELETE SET NULL,
  topic_id UUID NULL REFERENCES topics(id) ON DELETE SET NULL,

  feedback_type feedback_type NOT NULL,
  message TEXT NULL,

  status feedback_status NOT NULL DEFAULT 'new',
  triaged_at TIMESTAMPTZ NULL,
  triaged_by_user_id UUID NULL,
  resolved_at TIMESTAMPTZ NULL,
  resolved_by_user_id UUID NULL,
  resolution_notes TEXT NULL,

  meta JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_feedback_reports_status_created_at ON feedback_reports (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_reports_cluster_created_at ON feedback_reports (cluster_id, created_at DESC);

-- --- editorial_actions (append-only audit log) ------------------------------
CREATE TABLE IF NOT EXISTS editorial_actions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  actor_type editor_actor_type NOT NULL DEFAULT 'admin_token',
  actor_user_id UUID NULL,

  action_type editorial_action_type NOT NULL,

  target_cluster_id UUID NULL REFERENCES story_clusters(id) ON DELETE SET NULL,
  target_topic_id UUID NULL REFERENCES topics(id) ON DELETE SET NULL,
  target_source_id UUID NULL REFERENCES sources(id) ON DELETE SET NULL,
  target_lineage_node_id UUID NULL REFERENCES lineage_nodes(id) ON DELETE SET NULL,
  target_lineage_edge_id UUID NULL REFERENCES lineage_edges(id) ON DELETE SET NULL,
  target_feedback_id UUID NULL REFERENCES feedback_reports(id) ON DELETE SET NULL,

  notes TEXT NULL,
  supporting_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE editorial_actions
  ADD CONSTRAINT editorial_actions_supporting_item_ids_is_array
  CHECK (jsonb_typeof(supporting_item_ids) = 'array')
  NOT VALID;

CREATE INDEX IF NOT EXISTS idx_editorial_actions_created_at ON editorial_actions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_editorial_actions_action_type_created_at ON editorial_actions (action_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_editorial_actions_cluster_created_at ON editorial_actions (target_cluster_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_editorial_actions_topic_created_at ON editorial_actions (target_topic_id, created_at DESC);

-- Stage 5 accounts are optional in authless-first deployments.
-- Add FK constraints to users only when the users table exists.
DO $$
BEGIN
  IF to_regclass('public.users') IS NOT NULL THEN
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'feedback_reports_user_id_fkey'
    ) THEN
      ALTER TABLE feedback_reports
        ADD CONSTRAINT feedback_reports_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'feedback_reports_triaged_by_user_id_fkey'
    ) THEN
      ALTER TABLE feedback_reports
        ADD CONSTRAINT feedback_reports_triaged_by_user_id_fkey
        FOREIGN KEY (triaged_by_user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'feedback_reports_resolved_by_user_id_fkey'
    ) THEN
      ALTER TABLE feedback_reports
        ADD CONSTRAINT feedback_reports_resolved_by_user_id_fkey
        FOREIGN KEY (resolved_by_user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'editorial_actions_actor_user_id_fkey'
    ) THEN
      ALTER TABLE editorial_actions
        ADD CONSTRAINT editorial_actions_actor_user_id_fkey
        FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
  END IF;
END$$;

-- --- cluster_topics: manual assignment source + lock ------------------------
ALTER TABLE cluster_topics
  ADD COLUMN IF NOT EXISTS assignment_source topic_assignment_source NOT NULL DEFAULT 'auto',
  ADD COLUMN IF NOT EXISTS locked BOOLEAN NOT NULL DEFAULT false;

COMMIT;
