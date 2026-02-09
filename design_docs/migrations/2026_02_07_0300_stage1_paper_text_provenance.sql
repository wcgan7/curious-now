-- Stage 1/2: persist paper text provenance metadata.

BEGIN;

ALTER TABLE items
  ADD COLUMN IF NOT EXISTS full_text_kind TEXT NULL,
  ADD COLUMN IF NOT EXISTS full_text_license TEXT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'items_full_text_kind_check'
  ) THEN
    ALTER TABLE items
      ADD CONSTRAINT items_full_text_kind_check
      CHECK (
        full_text_kind IS NULL
        OR full_text_kind IN ('abstract', 'fulltext')
      );
  END IF;
END$$;

-- Backfill known rows from source provenance.
UPDATE items
SET full_text_kind = CASE
  WHEN full_text_source IN ('arxiv_api', 'crossref', 'openalex') THEN 'abstract'
  WHEN full_text_source IN (
    'landing_page',
    'arxiv_html',
    'arxiv_pdf',
    'arxiv_eprint',
    'unpaywall_pdf',
    'unpaywall_landing',
    'openalex_pdf',
    'openalex_landing',
    'crossref_pdf',
    'crossref_landing',
    'pmc_oa',
    'publisher_pdf'
  )
    THEN 'fulltext'
  ELSE full_text_kind
END
WHERE full_text IS NOT NULL
  AND btrim(full_text) <> ''
  AND full_text_kind IS NULL;

UPDATE items
SET full_text_license = 'arxiv'
WHERE full_text_source = 'arxiv_api'
  AND (full_text_license IS NULL OR btrim(full_text_license) = '');

CREATE INDEX IF NOT EXISTS idx_items_full_text_kind
  ON items (content_type, full_text_kind, full_text_status, fetched_at DESC)
  WHERE content_type IN ('preprint', 'peer_reviewed');

COMMIT;
