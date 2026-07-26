-- Curious Now v2 initial schema.
--
-- This is a fresh baseline, not a continuation of the v1 stage migrations.
-- V2 never writes to the v1 schema.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  homepage_url TEXT NULL,
  role TEXT NOT NULL CHECK (
    role IN (
      'primary_research',
      'journalism',
      'lab_announcement',
      'institutional',
      'government',
      'press_release',
      'discovery'
    )
  ),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  policy JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name)
);

CREATE TABLE source_feeds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  feed_kind TEXT NOT NULL DEFAULT 'rss' CHECK (feed_kind IN ('rss', 'atom', 'api')),
  default_content_type TEXT NOT NULL CHECK (
    default_content_type IN (
      'news',
      'lab_announcement',
      'press_release',
      'preprint',
      'peer_reviewed',
      'report',
      'blog',
      'dataset',
      'other'
    )
  ),
  fetch_interval_minutes INTEGER NOT NULL DEFAULT 60 CHECK (fetch_interval_minutes > 0),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  last_fetched_at TIMESTAMPTZ NULL,
  last_status TEXT NULL,
  etag TEXT NULL,
  last_modified TEXT NULL,
  error_streak INTEGER NOT NULL DEFAULT 0 CHECK (error_streak >= 0),
  next_fetch_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (url)
);

CREATE INDEX idx_source_feeds_due
  ON source_feeds (next_fetch_at)
  WHERE active = TRUE;

CREATE TABLE items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES sources(id),
  source_native_id TEXT NULL,
  url TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  canonical_hash CHAR(64) NOT NULL,
  title TEXT NOT NULL,
  snippet TEXT NULL,
  content_type TEXT NOT NULL CHECK (
    content_type IN (
      'news',
      'lab_announcement',
      'press_release',
      'preprint',
      'peer_reviewed',
      'report',
      'blog',
      'dataset',
      'other'
    )
  ),
  published_at TIMESTAMPTZ NULL,
  discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  doi TEXT NULL,
  arxiv_id TEXT NULL,
  pmid TEXT NULL,
  access_class TEXT NOT NULL DEFAULT 'metadata_only' CHECK (
    access_class IN ('metadata_only', 'snippet', 'abstract', 'open_full_text')
  ),
  text_ref TEXT NULL,
  text_sha256 CHAR(64) NULL,
  raw_ref TEXT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (canonical_hash)
);

CREATE UNIQUE INDEX idx_items_source_native_id
  ON items (source_id, source_native_id)
  WHERE source_native_id IS NOT NULL;

CREATE INDEX idx_items_published_at ON items (published_at DESC);
CREATE INDEX idx_items_doi ON items (lower(doi)) WHERE doi IS NOT NULL;
CREATE INDEX idx_items_arxiv_id ON items (lower(arxiv_id)) WHERE arxiv_id IS NOT NULL;
CREATE INDEX idx_items_pmid ON items (pmid) WHERE pmid IS NOT NULL;

CREATE TABLE papers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  doi TEXT NULL,
  arxiv_id TEXT NULL,
  pmid TEXT NULL,
  publication_date DATE NULL,
  venue TEXT NULL,
  abstract TEXT NULL,
  full_text_ref TEXT NULL,
  full_text_sha256 CHAR(64) NULL,
  access_class TEXT NOT NULL DEFAULT 'metadata_only' CHECK (
    access_class IN ('metadata_only', 'abstract', 'open_full_text')
  ),
  external_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_papers_doi ON papers (lower(doi)) WHERE doi IS NOT NULL;
CREATE UNIQUE INDEX idx_papers_arxiv_id ON papers (lower(arxiv_id)) WHERE arxiv_id IS NOT NULL;
CREATE UNIQUE INDEX idx_papers_pmid ON papers (pmid) WHERE pmid IS NOT NULL;

CREATE TABLE item_papers (
  item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  match_kind TEXT NOT NULL CHECK (
    match_kind IN ('doi', 'arxiv_id', 'pmid', 'source_metadata', 'reviewed')
  ),
  match_confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0 CHECK (
    match_confidence >= 0 AND match_confidence <= 1
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (item_id, paper_id)
);

CREATE TABLE stories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'hidden')),
  published_at TIMESTAMPTZ NULL,
  last_evidence_at TIMESTAMPTZ NULL,
  feed_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  ranking_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
  ranked_at TIMESTAMPTZ NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  search_document TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(canonical_title, ''))
  ) STORED
);

CREATE INDEX idx_stories_feed
  ON stories (feed_score DESC, published_at DESC, id DESC)
  WHERE status = 'published';

CREATE INDEX idx_stories_latest
  ON stories (published_at DESC, id DESC)
  WHERE status = 'published';

CREATE INDEX idx_stories_search ON stories USING GIN (search_document);

CREATE TABLE story_items (
  story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (
    role IN ('primary_evidence', 'independent_coverage', 'announcement', 'context', 'discovery')
  ),
  cluster_method TEXT NOT NULL CHECK (
    cluster_method IN (
      'paper_identifier',
      'canonical_url',
      'bibliographic',
      'similarity',
      'operator'
    )
  ),
  cluster_score DOUBLE PRECISION NOT NULL DEFAULT 1.0 CHECK (
    cluster_score >= 0 AND cluster_score <= 1
  ),
  cluster_reason JSONB NOT NULL DEFAULT '{}'::jsonb,
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (story_id, item_id)
);

CREATE INDEX idx_story_items_item ON story_items (item_id);

CREATE TABLE evidence_packets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  version INTEGER NOT NULL CHECK (version > 0),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (
    status IN ('draft', 'valid', 'invalid', 'superseded')
  ),
  text_sufficiency TEXT NOT NULL DEFAULT 'metadata_only' CHECK (
    text_sufficiency IN ('metadata_only', 'snippet', 'abstract', 'open_full_text')
  ),
  central_claim TEXT NULL,
  why_it_matters JSONB NOT NULL DEFAULT '[]'::jsonb,
  limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
  uncertainties JSONB NOT NULL DEFAULT '[]'::jsonb,
  important_numbers JSONB NOT NULL DEFAULT '[]'::jsonb,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at TIMESTAMPTZ NULL,
  UNIQUE (story_id, version)
);

ALTER TABLE stories
  ADD COLUMN current_evidence_packet_id UUID NULL
  REFERENCES evidence_packets(id);

CREATE INDEX idx_evidence_packets_story
  ON evidence_packets (story_id, version DESC);

CREATE TABLE evidence_claims (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  evidence_packet_id UUID NOT NULL REFERENCES evidence_packets(id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  claim_kind TEXT NOT NULL CHECK (
    claim_kind IN (
      'observation',
      'result',
      'method',
      'comparison',
      'limitation',
      'uncertainty',
      'context'
    )
  ),
  claim_text TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (evidence_packet_id, ordinal)
);

CREATE TABLE claim_evidence (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id UUID NOT NULL REFERENCES evidence_claims(id) ON DELETE CASCADE,
  item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  support_kind TEXT NOT NULL CHECK (
    support_kind IN ('direct', 'metadata', 'context', 'contradicting')
  ),
  excerpt TEXT NULL,
  locator JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (claim_id, item_id, support_kind)
);

CREATE INDEX idx_claim_evidence_item ON claim_evidence (item_id);

CREATE TABLE explanations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  evidence_packet_id UUID NOT NULL REFERENCES evidence_packets(id) ON DELETE CASCADE,
  depth TEXT NOT NULL CHECK (depth IN ('glance', 'explain', 'technical')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (
    status IN ('pending', 'valid', 'invalid', 'failed', 'superseded')
  ),
  content JSONB NOT NULL DEFAULT '{}'::jsonb,
  plain_text TEXT NULL,
  model_provider TEXT NULL,
  model_name TEXT NULL,
  prompt_version TEXT NOT NULL,
  input_tokens INTEGER NULL CHECK (input_tokens IS NULL OR input_tokens >= 0),
  output_tokens INTEGER NULL CHECK (output_tokens IS NULL OR output_tokens >= 0),
  failure_reason TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at TIMESTAMPTZ NULL,
  UNIQUE (evidence_packet_id, depth, prompt_version)
);

CREATE INDEX idx_explanations_story_depth
  ON explanations (story_id, depth, created_at DESC);

CREATE TABLE topics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  description TEXT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (slug)
);

CREATE TABLE story_topics (
  story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  assignment_kind TEXT NOT NULL CHECK (
    assignment_kind IN ('rule', 'model', 'operator')
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (story_id, topic_id)
);

CREATE INDEX idx_story_topics_topic ON story_topics (topic_id, story_id);

CREATE TABLE concepts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  short_explanation TEXT NULL,
  explanation JSONB NOT NULL DEFAULT '{}'::jsonb,
  explanation_version TEXT NULL,
  status TEXT NOT NULL DEFAULT 'candidate' CHECK (
    status IN ('candidate', 'published', 'hidden')
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (slug)
);

CREATE TABLE concept_aliases (
  concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  normalized_alias TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (concept_id, normalized_alias)
);

CREATE INDEX idx_concept_aliases_lookup ON concept_aliases (normalized_alias);

CREATE TABLE concept_edges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  to_concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  relation TEXT NOT NULL CHECK (
    relation IN ('requires', 'related_to', 'part_of', 'example_of', 'contrasts_with')
  ),
  status TEXT NOT NULL DEFAULT 'candidate' CHECK (
    status IN ('candidate', 'published', 'rejected')
  ),
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at TIMESTAMPTZ NULL,
  CHECK (from_concept_id <> to_concept_id),
  UNIQUE (from_concept_id, to_concept_id, relation)
);

CREATE INDEX idx_concept_edges_to ON concept_edges (to_concept_id, relation);

CREATE TABLE story_concepts (
  story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  relevance TEXT NOT NULL CHECK (relevance IN ('prerequisite', 'central', 'mentioned')),
  confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (story_id, concept_id)
);

CREATE TABLE paper_relations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  to_paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  relation TEXT NOT NULL CHECK (
    relation IN ('cites', 'extends', 'replicates', 'contradicts', 'applies')
  ),
  source TEXT NOT NULL CHECK (
    source IN ('bibliographic_api', 'paper_text', 'operator')
  ),
  evidence_item_id UUID NULL REFERENCES items(id) ON DELETE SET NULL,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (from_paper_id <> to_paper_id),
  UNIQUE (from_paper_id, to_paper_id, relation)
);

CREATE INDEX idx_paper_relations_to ON paper_relations (to_paper_id, relation);

CREATE TABLE pipeline_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'partial')),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ NULL,
  counters JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_summary TEXT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_pipeline_runs_job_started
  ON pipeline_runs (job_name, started_at DESC);

CREATE TABLE feed_fetches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_feed_id UUID NOT NULL REFERENCES source_feeds(id) ON DELETE CASCADE,
  pipeline_run_id UUID NULL REFERENCES pipeline_runs(id) ON DELETE SET NULL,
  status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed', 'not_modified')),
  http_status INTEGER NULL,
  items_seen INTEGER NOT NULL DEFAULT 0 CHECK (items_seen >= 0),
  error_message TEXT NULL,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_feed_fetches_feed_started
  ON feed_fetches (source_feed_id, started_at DESC);

INSERT INTO schema_migrations (version) VALUES ('0001_initial');

COMMIT;
