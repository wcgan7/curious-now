-- 2026_02_03_0500_stage6_notifications_digests.sql
-- Stage 6: notifications + digests (email-first) + story watches.
-- Matches design_docs/stage6.md. Uses UUIDs everywhere (see design_docs/decisions.md).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'notification_channel') THEN
    CREATE TYPE notification_channel AS ENUM ('email', 'in_app', 'push');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'notification_type') THEN
    CREATE TYPE notification_type AS ENUM ('cluster_update', 'topic_digest');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'notification_status') THEN
    CREATE TYPE notification_status AS ENUM ('queued', 'sending', 'sent', 'error', 'canceled');
  END IF;
END$$;

-- --- user_cluster_watches ---------------------------------------------------
CREATE TABLE IF NOT EXISTS user_cluster_watches (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_user_cluster_watches_cluster_user ON user_cluster_watches (cluster_id, user_id);

-- --- notification_jobs ------------------------------------------------------
CREATE TABLE IF NOT EXISTS notification_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

  channel notification_channel NOT NULL DEFAULT 'email',
  notification_type notification_type NOT NULL,
  status notification_status NOT NULL DEFAULT 'queued',

  dedupe_key TEXT NOT NULL,
  scheduled_for TIMESTAMPTZ NOT NULL DEFAULT now(),

  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT NULL,
  provider_message_id TEXT NULL,

  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  rendered_subject TEXT NULL,
  rendered_text TEXT NULL,
  rendered_html TEXT NULL,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sent_at TIMESTAMPTZ NULL,

  CONSTRAINT notification_jobs_dedupe_unique UNIQUE (dedupe_key)
);

CREATE INDEX IF NOT EXISTS idx_notification_jobs_status_scheduled_for ON notification_jobs (status, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_notification_jobs_user_created_at ON notification_jobs (user_id, created_at DESC);

DROP TRIGGER IF EXISTS trg_notification_jobs_set_updated_at ON notification_jobs;
CREATE TRIGGER trg_notification_jobs_set_updated_at
BEFORE UPDATE ON notification_jobs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;

