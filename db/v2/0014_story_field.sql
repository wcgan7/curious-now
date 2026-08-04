-- What a story is about, so a reader can ask for one field and not another.
--
-- The field is derived from reading the story, not from the feed it came down.
-- Source-derived tagging was measured against a classifier over 150 random
-- stories and disagreed on a third of them, nearly always because the venue was
-- wrong: arXiv's physical sciences feed carries geology, planetary science and
-- materials science; Google Research publishes on satellites and dermatology;
-- Nature publishes everything.
--
-- A LEAF is stored, never a group. The 33 leaves sit in 8 groups in
-- config/v2/fields.json, and the reader groups them for display, so promoting
-- mathematics to the top level once there is enough of it is an edit to that
-- file -- no re-tagging, no migration, and every story already carries the
-- finer answer.
--
-- Nullable on purpose. NULL means we have not established one, which is a
-- different thing from any leaf, and has to stay different: a story filed by
-- guesswork would appear under a field its reader did not ask for. The 33
-- values are not constrained here for the same reason the taxonomy is a file --
-- a CHECK would make regrouping a migration.

ALTER TABLE stories ADD COLUMN IF NOT EXISTS field text;

COMMENT ON COLUMN stories.field IS
  'Leaf of the field taxonomy in config/v2/fields.json. NULL where reading the '
  'story established none. Groups are a display concern and are not stored.';

-- The feed filters on this and orders by the sort key, so the two travel
-- together.
CREATE INDEX IF NOT EXISTS stories_field_effective_at_idx
  ON stories (field, effective_at DESC)
  WHERE status = 'published';
