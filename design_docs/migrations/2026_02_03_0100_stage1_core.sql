-- 2026_02_03_0100_stage1_core.sql
-- Stage 1: core ingestion tables (sources, feeds, items) + fetch logs.
-- Assumes Postgres and UUID primary keys (see design_docs/decisions.md).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- --- Enums (Stage 1) --------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'source_type') THEN
    CREATE TYPE source_type AS ENUM (
      'journalism',
      'journal',
      'preprint_server',
      'university',
      'government',
      'lab',
      'blog'
    );
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reliability_tier') THEN
    CREATE TYPE reliability_tier AS ENUM ('tier1', 'tier2', 'tier3');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'feed_type') THEN
    CREATE TYPE feed_type AS ENUM ('rss', 'atom', 'api');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'content_type') THEN
    CREATE TYPE content_type AS ENUM (
      'news',
      'press_release',
      'preprint',
      'peer_reviewed',
      'report'
    );
  END IF;
END$$;

-- --- Common updated_at trigger ----------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- --- sources ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  homepage_url TEXT NULL,
  source_type source_type NOT NULL,
  reliability_tier reliability_tier NULL,
  terms_notes TEXT NULL,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT sources_name_unique UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_sources_active ON sources (active) WHERE active = true;

DROP TRIGGER IF EXISTS trg_sources_set_updated_at ON sources;
CREATE TRIGGER trg_sources_set_updated_at
BEFORE UPDATE ON sources
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- --- source_feeds -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS source_feeds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  feed_url TEXT NOT NULL,
  feed_type feed_type NOT NULL,
  fetch_interval_minutes INT NOT NULL DEFAULT 30,
  last_fetched_at TIMESTAMPTZ NULL,
  last_status INT NULL,
  error_streak INT NOT NULL DEFAULT 0,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT source_feeds_source_feed_url_unique UNIQUE (source_id, feed_url)
);

CREATE INDEX IF NOT EXISTS idx_source_feeds_source_id ON source_feeds (source_id);
CREATE INDEX IF NOT EXISTS idx_source_feeds_last_fetched_at ON source_feeds (last_fetched_at);
CREATE INDEX IF NOT EXISTS idx_source_feeds_active ON source_feeds (active) WHERE active = true;

DROP TRIGGER IF EXISTS trg_source_feeds_set_updated_at ON source_feeds;
CREATE TRIGGER trg_source_feeds_set_updated_at
BEFORE UPDATE ON source_feeds
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- --- items ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  title TEXT NOT NULL,
  published_at TIMESTAMPTZ NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  author TEXT NULL,
  snippet TEXT NULL,
  content_type content_type NOT NULL,
  paywalled BOOLEAN NULL,
  language TEXT NOT NULL DEFAULT 'en',
  raw_ref TEXT NULL,
  title_hash TEXT NOT NULL,
  canonical_hash TEXT NOT NULL,

  -- External IDs (useful for clustering and trust)
  arxiv_id TEXT NULL,
  doi TEXT NULL,
  pmid TEXT NULL,
  external_ids JSONB NULL,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT items_canonical_hash_unique UNIQUE (canonical_hash)
);

CREATE INDEX IF NOT EXISTS idx_items_published_at ON items (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_source_published ON items (source_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_title_hash ON items (title_hash);
CREATE INDEX IF NOT EXISTS idx_items_arxiv_id ON items (arxiv_id) WHERE arxiv_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_doi ON items (doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_pmid ON items (pmid) WHERE pmid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_external_ids_gin ON items USING GIN (external_ids);

DROP TRIGGER IF EXISTS trg_items_set_updated_at ON items;
CREATE TRIGGER trg_items_set_updated_at
BEFORE UPDATE ON items
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- --- feed_fetch_logs (ops/debug) -------------------------------------------
CREATE TABLE IF NOT EXISTS feed_fetch_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  feed_id UUID NOT NULL REFERENCES source_feeds(id) ON DELETE CASCADE,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ NULL,
  status TEXT NOT NULL CHECK (status IN ('success', 'error')),
  http_status INT NULL,
  duration_ms INT NULL,
  error_message TEXT NULL,
  items_seen INT NOT NULL DEFAULT 0,
  items_upserted INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feed_fetch_logs_feed_started ON feed_fetch_logs (feed_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_feed_fetch_logs_started_at ON feed_fetch_logs (started_at DESC);

COMMIT;

