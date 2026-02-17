-- 2026_02_14_0100_stage1_backfill_content_type.sql
-- Backfill content_type using the multi-signal cascade introduced in ingestion.py.
-- Fixes items ingested before the cascade was added, where content_type was
-- assigned solely from source_type and missed arXiv ID, domain, and TLD signals.

BEGIN;

-- Helper: extract hostname from a URL  (e.g. 'https://www.science.org/doi/...' → 'www.science.org')
CREATE OR REPLACE FUNCTION _tmp_url_host(u text) RETURNS text
  LANGUAGE sql IMMUTABLE AS $$
    SELECT lower(split_part(split_part(u, '://', 2), '/', 1))
  $$;

-- Signal 1: arXiv ID present → preprint
UPDATE items
SET    content_type = 'preprint'
WHERE  arxiv_id IS NOT NULL
  AND  content_type <> 'preprint';

-- Signal 2: URL domain = preprint server → preprint
UPDATE items
SET    content_type = 'preprint'
WHERE  arxiv_id IS NULL
  AND  content_type <> 'preprint'
  AND  _tmp_url_host(url) IN (
         'arxiv.org',
         'biorxiv.org',  'www.biorxiv.org',
         'medrxiv.org',  'www.medrxiv.org',
         'ssrn.com',
         'chemrxiv.org'
       );

-- Signal 3: URL domain = known journal → peer_reviewed
-- (Skip nature.com — needs path-level logic already handled at ingest time)
UPDATE items
SET    content_type = 'peer_reviewed'
WHERE  arxiv_id IS NULL
  AND  content_type NOT IN ('preprint', 'peer_reviewed')
  AND  _tmp_url_host(url) IN (
         'science.org',           'www.science.org',
         'cell.com',              'www.cell.com',
         'thelancet.com',         'www.thelancet.com',
         'nejm.org',              'www.nejm.org',
         'pnas.org',              'www.pnas.org',
         'journals.plos.org',
         'frontiersin.org',       'www.frontiersin.org',
         'link.springer.com',
         'www.sciencedirect.com',
         'academic.oup.com',
         'onlinelibrary.wiley.com',
         'www.mdpi.com',
         'iopscience.iop.org',
         'pubs.acs.org',
         'journals.aps.org',
         'bmj.com',               'www.bmj.com',
         'jamanetwork.com',
         'jci.org',               'www.jci.org',
         'elifesciences.org'
       );

-- Signal 4: .edu / .ac.uk suffix → press_release
UPDATE items
SET    content_type = 'press_release'
WHERE  arxiv_id IS NULL
  AND  content_type = 'news'
  AND  (_tmp_url_host(url) LIKE '%.edu' OR _tmp_url_host(url) LIKE '%.ac.uk');

-- Signal 5: .gov / .gov.uk suffix → report
UPDATE items
SET    content_type = 'report'
WHERE  arxiv_id IS NULL
  AND  content_type = 'news'
  AND  (_tmp_url_host(url) LIKE '%.gov' OR _tmp_url_host(url) LIKE '%.gov.uk');

-- Also sync full_text_status for items newly classified as preprint/peer_reviewed
-- that don't yet have full text fetched.
UPDATE items
SET    full_text_status = 'pending'
WHERE  content_type IN ('preprint', 'peer_reviewed')
  AND  (full_text IS NULL OR btrim(full_text) = '')
  AND  (full_text_status IS NULL);

-- Clean up temp function
DROP FUNCTION _tmp_url_host(text);

COMMIT;
