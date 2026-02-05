-- 2026_02_03_0400_stage5_accounts_personalization.sql
-- Stage 5: accounts + sessions + user prefs + follows/blocks/saves/hides + engagement events.
-- Matches design_docs/stage5.md and uses UUIDs everywhere (see design_docs/decisions.md).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reading_mode') THEN
    CREATE TYPE reading_mode AS ENUM ('intuition', 'deep');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'engagement_event_type') THEN
    CREATE TYPE engagement_event_type AS ENUM (
      'open_cluster',
      'click_item',
      'save_cluster',
      'unsave_cluster',
      'hide_cluster',
      'unhide_cluster',
      'follow_topic',
      'unfollow_topic',
      'block_source',
      'unblock_source'
    );
  END IF;
END$$;

-- --- users -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_normalized TEXT NOT NULL,
  email_raw TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ NULL,

  CONSTRAINT users_email_normalized_unique UNIQUE (email_normalized)
);

DROP TRIGGER IF EXISTS trg_users_set_updated_at ON users;
CREATE TRIGGER trg_users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- --- user_sessions ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_token_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ NULL,
  user_agent TEXT NULL,
  ip_hash TEXT NULL,

  CONSTRAINT user_sessions_token_unique UNIQUE (session_token_hash)
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_expires ON user_sessions (user_id, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions (expires_at DESC);

-- --- auth_magic_link_tokens -------------------------------------------------
CREATE TABLE IF NOT EXISTS auth_magic_link_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ NULL,
  user_agent TEXT NULL,
  ip_hash TEXT NULL,

  CONSTRAINT auth_magic_link_tokens_token_unique UNIQUE (token_hash)
);

CREATE INDEX IF NOT EXISTS idx_auth_magic_link_tokens_user_created ON auth_magic_link_tokens (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_auth_magic_link_tokens_expires ON auth_magic_link_tokens (expires_at DESC);

-- --- user_prefs -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_prefs (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  reading_mode_default reading_mode NOT NULL DEFAULT 'intuition',
  notification_settings JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_user_prefs_set_updated_at ON user_prefs;
CREATE TRIGGER trg_user_prefs_set_updated_at
BEFORE UPDATE ON user_prefs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- --- user_topic_follows -----------------------------------------------------
CREATE TABLE IF NOT EXISTS user_topic_follows (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, topic_id)
);

CREATE INDEX IF NOT EXISTS idx_user_topic_follows_topic_user ON user_topic_follows (topic_id, user_id);

-- --- user_source_blocks -----------------------------------------------------
CREATE TABLE IF NOT EXISTS user_source_blocks (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_user_source_blocks_source_user ON user_source_blocks (source_id, user_id);

-- --- user_cluster_saves -----------------------------------------------------
CREATE TABLE IF NOT EXISTS user_cluster_saves (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_user_cluster_saves_user_created ON user_cluster_saves (user_id, created_at DESC);

-- --- user_cluster_hides -----------------------------------------------------
CREATE TABLE IF NOT EXISTS user_cluster_hides (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_user_cluster_hides_user_created ON user_cluster_hides (user_id, created_at DESC);

-- --- engagement_events ------------------------------------------------------
CREATE TABLE IF NOT EXISTS engagement_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
  client_id UUID NULL,
  event_type engagement_event_type NOT NULL,
  cluster_id UUID NULL REFERENCES story_clusters(id) ON DELETE SET NULL,
  item_id UUID NULL REFERENCES items(id) ON DELETE SET NULL,
  topic_id UUID NULL REFERENCES topics(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  meta JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_engagement_events_user_created ON engagement_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_engagement_events_client_created ON engagement_events (client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_engagement_events_cluster_created ON engagement_events (cluster_id, created_at DESC);

COMMIT;

