-- Content type stopped being a per-feed guess.
--
-- `source_feeds.default_content_type` was copied onto every item and then read
-- by four consumers as though it were established: the reader printed "Peer
-- reviewed" from it, ranking scored it 1.0, the publication logic counted the
-- item as a paper, and the generation prompts announced it to the model. For a
-- feed that carries research, news, comment and book reviews down one URL, that
-- default is wrong more often than it is right — 46 of 75 Nature items in the
-- corpus at the time of writing.
--
-- Two changes. Feeds may now carry rules that decide the type per item from its
-- URL or DOI, so a default is only used when nothing better applies. And items
-- record where their type came from, so a claim made to a reader can be traced
-- to evidence rather than to a guess.

BEGIN;

ALTER TABLE source_feeds
  ADD COLUMN content_type_rules JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN source_feeds.content_type_rules IS
  'Ordered [{pattern, content_type}]; first pattern found in an item URL or DOI '
  'wins, else default_content_type.';

ALTER TABLE items
  ADD COLUMN content_type_basis TEXT NOT NULL DEFAULT 'feed_default'
    CHECK (content_type_basis IN (
      'feed_default',   -- the feed carries one kind of thing and said which
      'feed_unmatched', -- the feed is mixed and this item matched no rule
      'source_pattern', -- matched a rule on this item's own URL or DOI
      'document',       -- the retrieved document's structure
      'classifier'      -- the evidence packet's judgement of what the item is
    )),
  ADD COLUMN content_type_note TEXT NULL;

COMMENT ON COLUMN items.content_type_basis IS
  'Where content_type came from. Every value except feed_unmatched may support '
  'a review-status claim: a feed with no rules carries one kind of item and its '
  'default describes them, where a feed with rules is known to be mixed and an '
  'item matching none of them is genuinely unclassified.';

-- Existing rows all predate any per-item judgement, so they keep the honest
-- label rather than inheriting a confidence they were never given.
UPDATE items SET content_type_basis = 'feed_default';

CREATE INDEX idx_items_content_type_basis
  ON items (content_type_basis)
  WHERE content_type_basis = 'feed_default';

INSERT INTO schema_migrations (version) VALUES ('0006_content_type_provenance');

COMMIT;
