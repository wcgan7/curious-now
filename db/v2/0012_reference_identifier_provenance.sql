-- How a reference's identifier was arrived at, and how much to trust it.
--
-- Two kinds of identifier end up in the same columns and they are not equally
-- good. One is parsed from the publisher's own markup -- a <pub-id> element, a
-- doi.org href -- and is exact. The other is recovered by searching a citation
-- string against an external index, and is a judgement that can be wrong.
--
-- The distinction has to be recorded because a wrong identifier is worse than a
-- missing one: it creates a paper that does not exist and an edge that points
-- at it, and nothing downstream could tell that apart from a real one. 35% of
-- this corpus's 26,563 references carry no identifier in their markup at all --
-- 62% within arXiv, where conference papers are cited without DOIs -- so the
-- recovered kind will not be a rare case.

BEGIN;

ALTER TABLE item_references
  ADD COLUMN identifier_source TEXT NULL
    CHECK (identifier_source IN ('markup', 'crossref_bibliographic')),
  ADD COLUMN identifier_confidence DOUBLE PRECISION NULL
    CHECK (identifier_confidence >= 0 AND identifier_confidence <= 1);

COMMENT ON COLUMN item_references.identifier_source IS
  'markup: taken from the document, exact. crossref_bibliographic: matched '
  'from the citation string, and only as good as its confidence.';

COMMENT ON COLUMN item_references.identifier_confidence IS
  'Agreement between the matched work and the citation string. 1.0 for '
  'anything read from markup.';

-- Everything already stored was parsed from a document.
UPDATE item_references
   SET identifier_source = 'markup', identifier_confidence = 1.0
 WHERE doi IS NOT NULL OR arxiv_id IS NOT NULL;

-- The rescue reads this: entries still worth looking up are the ones with no
-- identifier that the body actually cited.
CREATE INDEX item_references_unresolved_idx
  ON item_references (mentions DESC)
  WHERE doi IS NULL AND arxiv_id IS NULL;

INSERT INTO schema_migrations (version) VALUES ('0012_reference_identifier_provenance');

COMMIT;
