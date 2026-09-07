-- A few useful publishers expose their full archive in one RSS document.
-- Keep those sources declarative while preventing a first poll from importing
-- years of stale entries.

BEGIN;

ALTER TABLE source_feeds
  ADD COLUMN max_entries INTEGER NULL CHECK (max_entries > 0);

COMMENT ON COLUMN source_feeds.max_entries IS
  'Maximum publisher-ordered entries considered per fetch; NULL is unlimited.';

INSERT INTO schema_migrations (version) VALUES ('0015_feed_entry_limits');

COMMIT;
