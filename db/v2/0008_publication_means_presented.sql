-- Publication comes to mean what PRODUCT.md already said it means.
--
-- A story was published the moment it was ingested, carrying its source's own
-- RSS headline, and the gate then re-published it on word count alone. So the
-- feed was 295 stories of which 8 had an explanation: 287 cards showing someone
-- else's headline and opening on "a grounded explanation is not available yet"
-- — the hype-carrying titles the Title contract exists to replace.
--
-- From here, only a validated presentation set publishes a story. The gate
-- decides eligibility and records it in supported_depths; generation decides
-- publication, because only generation knows whether anything can be shown.
--
-- Withholding also becomes durable. `_withhold` set status to draft and nothing
-- more, so the next gate run published the story again and generation paid to
-- classify it again — the same podcast episode, every cycle, indefinitely. The
-- judgement is recorded on the story with the classifier version behind it, so
-- the gate leaves it alone and a later, better taxonomy can reconsider it.

BEGIN;

ALTER TABLE stories
  ADD COLUMN withheld_kind TEXT NULL,
  ADD COLUMN withheld_by TEXT NULL;

COMMENT ON COLUMN stories.withheld_kind IS
  'The story kind that disqualified this story — an announcement reports that '
  'something happened and leaves nothing to explain. The gate skips these.';
COMMENT ON COLUMN stories.withheld_by IS
  'Prompt version of the classifier that withheld it, so a story dropped under '
  'an older taxonomy can be reconsidered rather than dropped for good.';

CREATE INDEX idx_stories_awaiting_presentation
  ON stories (last_evidence_at DESC)
  WHERE status <> 'hidden' AND withheld_kind IS NULL;

-- Withdraw what was never presentable. These keep every row they had — they are
-- still evidence, still clusterable, still attributable — they simply stop
-- being offered to a reader as though they had been explained.
UPDATE stories SET
  status = 'draft',
  updated_at = now()
WHERE status = 'published'
  AND NOT EXISTS (
    SELECT 1 FROM explanations e
    WHERE e.story_id = stories.id AND e.status = 'valid'
  );

INSERT INTO schema_migrations (version) VALUES ('0008_publication_means_presented');

COMMIT;
