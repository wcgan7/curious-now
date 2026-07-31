-- The image a publisher syndicates with its own story.
--
-- Feed cards were text only, on a rule that banned "an image added merely to
-- increase card prominence". The rule mistook the mechanism for the harm: the
-- harm is a feed that competes for attention, and a column of forty identical
-- text cards is harder to scan than one the eye can travel through. Withdrawn
-- in READER_EXPERIENCE.md, along with the reasoning.
--
-- What is stored is a URL and nothing else. The image itself stays on the
-- publisher's CDN, fetched by the reader's browser from the same feed element
-- the publisher populated so that readers could display it — media:content,
-- media:thumbnail, or an image enclosure. Nothing is copied, so nothing here
-- needs a licence we do not have.
--
-- Around half the corpus will never have one. No preprint server or journal
-- syndicates images: arXiv 0 of 519 entries, medRxiv 0 of 30, Nature 0 of 75,
-- against 100% for Google Research, the BBC, STAT, Science News, NVIDIA and
-- Quanta. Absence is the common case and the card must be whole without it.

BEGIN;

ALTER TABLE items
  ADD COLUMN image_url TEXT NULL;

COMMENT ON COLUMN items.image_url IS
  'Image URL syndicated in the source feed entry. Hotlinked, never copied; '
  'NULL for every paper source.';

INSERT INTO schema_migrations (version) VALUES ('0009_syndicated_images');

COMMIT;
