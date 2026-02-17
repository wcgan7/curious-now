-- Stage 5: Users, authentication, preferences, and user actions
-- Required by: repo_stage5.py, repo_stage6.py, notifications.py, retention.py

-- 1. Users table
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_normalized TEXT NOT NULL UNIQUE,
  email_raw TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ
);

-- 2. Magic link authentication tokens
CREATE TABLE IF NOT EXISTS auth_magic_link_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_magic_link_tokens_hash
  ON auth_magic_link_tokens (token_hash) WHERE used_at IS NULL;

-- 3. User sessions
CREATE TABLE IF NOT EXISTS user_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_hash
  ON user_sessions (session_token_hash) WHERE revoked_at IS NULL;

-- 4. User preferences
CREATE TABLE IF NOT EXISTS user_prefs (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  reading_mode_default TEXT NOT NULL DEFAULT 'intuition',
  notification_settings JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- 5. User topic follows
CREATE TABLE IF NOT EXISTS user_topic_follows (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, topic_id)
);

-- 6. User source blocks
CREATE TABLE IF NOT EXISTS user_source_blocks (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, source_id)
);

-- 7. User cluster saves (bookmarks)
CREATE TABLE IF NOT EXISTS user_cluster_saves (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, cluster_id)
);

-- 8. User cluster hides
CREATE TABLE IF NOT EXISTS user_cluster_hides (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, cluster_id)
);

-- 9. User cluster watches (Stage 6)
CREATE TABLE IF NOT EXISTS user_cluster_watches (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, cluster_id)
);

-- 10. Notification jobs
CREATE TABLE IF NOT EXISTS notification_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  channel TEXT NOT NULL DEFAULT 'email',
  notification_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  dedupe_key TEXT UNIQUE,
  scheduled_for TIMESTAMPTZ,
  sent_at TIMESTAMPTZ,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notification_jobs_queued
  ON notification_jobs (scheduled_for) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS idx_notification_jobs_sent
  ON notification_jobs (sent_at) WHERE sent_at IS NOT NULL;
