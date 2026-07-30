-- Two ways for a source to stop costing what it does not return.
--
-- A feed can carry entries that are not readable items at all. The BBC's
-- science feed includes its live radio schedule, whose text is whatever is on
-- air and different every hour, and video pages with no transcript behind them.
-- Both were being ingested, fetched, retried on a fortnightly cycle, and — for
-- the ones with enough words — classified by a model before being withheld.
-- Recognising them by URL costs nothing and happens before any of that.
--
-- And a source can stop being worth reading at all. Deactivating one already
-- stopped its feed being polled, but nothing else consulted `active`: its
-- backlog stayed in the retrieval queue and its drafts in the generation queue,
-- so a source dropped for never returning anything went on being asked. OpenAI
-- was 1,052 items, 46 attempted, 46 refused, with a thousand more behind them.

BEGIN;

ALTER TABLE source_feeds
  ADD COLUMN exclude_patterns JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN source_feeds.exclude_patterns IS
  'URL substrings that are not readable items; matching feed entries are '
  'never ingested.';

-- Retrieval walks items by status and generation walks published stories;
-- neither joined to sources, so an inactive source was still worked on.
CREATE INDEX idx_items_source_active
  ON items (source_id)
  WHERE full_text IS NULL;

INSERT INTO schema_migrations (version) VALUES ('0007_feed_exclusions');

COMMIT;
