-- The feed's sort key, written once at publication and never recomputed.
--
-- feed_score could not be right for long. 35% of it was freshness on an
-- 18-hour half-life, so a stored value was wrong within hours of being written
-- and re-running the pass only shortened the window in which the feed was
-- wrong. 113 of 168 published stories sat at zero because the pass had no
-- caller after generation.
--
-- Combining quality and freshness by multiplication instead of addition fixes
-- that structurally. With score = Q · exp(-(now - t)/h), taking logarithms and
-- multiplying by h gives (t + h·ln Q) - now, and the clock term is identical
-- for every story, so it cancels out of every comparison. t + h·ln Q therefore
-- never needs recomputing. Stored as a time, it reads plainly: a story ranks as
-- if published earlier by an amount its shortcomings cost it.
--
-- The other four components of feed_score measured our own machinery -- whether
-- we obtained the paper, how much text our retrieval captured, how many outlets
-- picked it up -- rather than the science, and are gone. Provenance survives as
-- a badge on the story: peer-reviewed against preprint is a fact worth showing
-- a reader, not a claim about whether the work is interesting.

BEGIN;

ALTER TABLE stories
  ADD COLUMN quality_score DOUBLE PRECISION NULL
    CHECK (quality_score > 0 AND quality_score <= 1),
  -- The sort key. A time rather than a number because every factor converts to
  -- one: h·ln(factor) is an offset in hours, which is what makes an operator
  -- able to ask why one story outranks another and get a usable answer.
  ADD COLUMN effective_at TIMESTAMPTZ NULL,
  ADD COLUMN significance TEXT NULL
    CHECK (significance IN ('changes_practice', 'incremental', 'unclear'));

COMMENT ON COLUMN stories.effective_at IS
  'Feed sort key: the item publication date shifted earlier by h·ln(quality). '
  'Time-invariant, so it is written at publication and never recomputed.';

COMMENT ON COLUMN stories.quality_score IS
  'Rungs earned x significance. Never provenance, retrieval success, or press '
  'pickup.';

COMMENT ON COLUMN stories.significance IS
  'Whether the result would change what someone in the field does next, as '
  'judged from the packet evidence with a required verbatim quote.';

CREATE INDEX idx_stories_effective
  ON stories (effective_at DESC, id DESC)
  WHERE status = 'published';

INSERT INTO schema_migrations (version) VALUES ('0013_effective_at_ranking');

COMMIT;
