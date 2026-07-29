-- Curious Now v2 search support.
--
-- Story search must reach the text a reader can actually see: the story's own
-- title, the generated display title, and the retained source titles. Each
-- gets an indexed generated tsvector so search stays a plain Postgres query.

BEGIN;

ALTER TABLE items
  ADD COLUMN search_document TSVECTOR GENERATED ALWAYS AS (
    to_tsvector(
      'english',
      coalesce(title, '') || ' ' || coalesce(snippet, '')
    )
  ) STORED;

CREATE INDEX idx_items_search ON items USING GIN (search_document);

ALTER TABLE display_titles
  ADD COLUMN search_document TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(text, ''))
  ) STORED;

CREATE INDEX idx_display_titles_search
  ON display_titles USING GIN (search_document);

INSERT INTO schema_migrations (version) VALUES ('0003_search');

COMMIT;
