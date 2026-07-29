-- Curious Now v2 full-text storage.
--
-- Publication now requires text that can ground an explanation, so what was
-- retrieved, from where, and why the alternatives lost all has to be visible.

BEGIN;

ALTER TABLE items
  ADD COLUMN full_text TEXT NULL,
  -- The section, figure, and table map. Prose lives in full_text; this is what
  -- lets a Technical walkthrough cite a section or a figure by name.
  ADD COLUMN text_structure JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN full_text_kind TEXT NULL CHECK (
    full_text_kind IN ('abstract', 'fulltext')
  ),
  -- Which candidate won: arxiv_html, pmc_jats, oa_pdf, article_html, ...
  ADD COLUMN full_text_source TEXT NULL,
  ADD COLUMN full_text_status TEXT NOT NULL DEFAULT 'pending' CHECK (
    full_text_status IN (
      'pending',
      'ok',
      'paywalled',
      'blocked',
      'not_found',
      'error'
    )
  ),
  ADD COLUMN full_text_licence TEXT NULL,
  ADD COLUMN full_text_words INTEGER NULL CHECK (
    full_text_words IS NULL OR full_text_words >= 0
  ),
  ADD COLUMN full_text_score DOUBLE PRECISION NULL,
  ADD COLUMN full_text_attempted JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN full_text_error TEXT NULL,
  ADD COLUMN full_text_fetched_at TIMESTAMPTZ NULL;

-- Retrieval works through items that have never been tried, oldest first.
CREATE INDEX idx_items_text_pending
  ON items (discovered_at DESC)
  WHERE full_text_status = 'pending';

-- Operators need to see why sources fail, not just that they did.
CREATE INDEX idx_items_text_status
  ON items (full_text_status, full_text_source);

INSERT INTO schema_migrations (version) VALUES ('0004_full_text');

COMMIT;
