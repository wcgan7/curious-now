-- The raw bytes of everything we fetch, kept so we never have to fetch twice.
--
-- Until now retrieval parsed a response and discarded it. That made every
-- extraction change a re-fetch: recovering arXiv's display equations, then the
-- bibliographies, then Nature's reference markup, then medRxiv's actual papers
-- each meant asking publishers again for pages we had already been given. It is
-- slow, it is rude, and it is avoidable for a few hundred megabytes.
--
-- One row per CANDIDATE, not per item. Retrieval tries several copies of an
-- article and they are not interchangeable: a short eLife piece scores higher
-- as publisher HTML while only its JATS carries the reference list, so the
-- stored text and the stored bibliography already come from different fetches.
-- Re-extraction needs whichever one it is re-reading.
--
-- The bodies themselves are NOT here. They live in a content-addressed store on
-- disk, and this table records the digest that locates one. The split follows
-- the requirements: the rows are small, mutable and must survive a crash, while
-- the bodies are large, immutable, and recoverable by re-fetching. Only the
-- former needs a filesystem with real ownership and honest fsync, which is what
-- lets the bodies sit on a large external disk that could never host Postgres.
--
-- A digest rather than a path, because the content is the address: identical
-- bodies are stored once, and retrieval does fetch the same article twice under
-- different candidate names -- publisher_html and article_html came back
-- byte-identical at 231,143 bytes in this corpus.

BEGIN;

CREATE TABLE item_fetches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  -- The candidate this came from: arxiv_html, plos_jats, oa_pdf, article_html.
  source TEXT NOT NULL,
  parser TEXT NOT NULL,
  url TEXT NOT NULL,
  final_url TEXT NULL,
  status_code INTEGER NULL,
  content_type TEXT NULL,
  -- Locates the body in the blob store; not a path, because the store is
  -- content-addressed and its root is configuration, not data.
  body_sha256 TEXT NOT NULL CHECK (body_sha256 ~ '^[0-9a-f]{64}$'),
  -- Size before compression, so growth can be reasoned about without reading
  -- a single blob off the disk.
  body_bytes INTEGER NOT NULL CHECK (body_bytes >= 0),
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (item_id, source)
);

COMMENT ON TABLE item_fetches IS
  'What we fetched and where its body is stored, one row per retrieval '
  'candidate, so extraction can be changed and re-run without asking the '
  'publisher again. Bodies live in the content-addressed blob store.';

COMMENT ON COLUMN item_fetches.source IS
  'Which candidate produced this body. Not necessarily the one that won: the '
  'text and the bibliography routinely come from different fetches.';

COMMENT ON COLUMN item_fetches.body_sha256 IS
  'SHA-256 of the uncompressed body. The blob store key; a row whose blob is '
  'missing means that item needs fetching again, which is not an error.';

CREATE INDEX item_fetches_item_idx ON item_fetches (item_id);
CREATE INDEX item_fetches_source_idx ON item_fetches (source);
-- Blobs are shared between rows, so a sweep needs to find every referrer of a
-- digest before deciding a file is orphaned.
CREATE INDEX item_fetches_digest_idx ON item_fetches (body_sha256);

INSERT INTO schema_migrations (version) VALUES ('0011_item_fetches');

COMMIT;
