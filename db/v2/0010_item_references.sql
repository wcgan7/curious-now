-- Bibliography entries, with every place the body cited them.
--
-- Extraction previously discarded these: the arXiv reader decomposed
-- .ltx_bibliography before reading it, and the JATS reader scanned <body> only,
-- where <ref-list> lives in <back>. So a document's own account of what it
-- builds on was fetched, parsed, and thrown away.
--
-- A row is a reference AS THE CITING PAPER STATES IT, not a resolved work. It
-- may carry no identifier at all, and roughly half of arXiv entries do not:
-- conference papers are cited without a DOI. Resolving those against an
-- external index is a separate step that is allowed to fail visibly, which is
-- why doi and arxiv_id are nullable rather than a precondition for storing the
-- entry.
--
-- Measured on real documents: PLOS via publisher JATS gives 527 references at
-- 93% carrying an identifier; arXiv via LaTeXML gives 44% carrying one but
-- 100% linked to their in-text mentions, because <cite> names its target
-- anchor and the mapping never has to be guessed from the marker text.
--
-- `contexts` holds the sentences that did the citing. They are the point: a
-- reference's role is stated in the prose around the marker -- "we use the
-- method of", "in contrast to" -- and that sentence is what makes a typed edge
-- checkable rather than asserted. They are stored as a document because they
-- are always read with their reference and never queried apart from it.

BEGIN;

CREATE TABLE item_references (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  -- Which retrieval candidate supplied the bibliography. Often the same source
  -- as items.full_text_source and deliberately not required to be: a short
  -- eLife or PLOS piece scores higher as publisher HTML on prose while only
  -- its JATS carries the reference list. When these differ, the sentences in
  -- `contexts` come from that other copy of the article rather than from
  -- items.full_text, so nothing should assume they appear there verbatim.
  reference_source TEXT NOT NULL,
  -- The document's own anchor: LaTeXML's "bib.bib12", JATS' ref id. Unique
  -- within an item, and how in-text markers were matched to this entry.
  ref_key TEXT NOT NULL,
  label TEXT NULL,
  citation_text TEXT NOT NULL,
  doi TEXT NULL,
  arxiv_id TEXT NULL,
  -- Denormalised from contexts so ranking never has to open the document.
  mentions INTEGER NOT NULL DEFAULT 0 CHECK (mentions >= 0),
  cited_sections TEXT[] NOT NULL DEFAULT '{}',
  contexts JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (item_id, ref_key)
);

COMMENT ON TABLE item_references IS
  'Bibliography entries as the citing document states them, with the sentences '
  'that cited each one. Not resolved works: an entry may carry no identifier.';

COMMENT ON COLUMN item_references.mentions IS
  'Times the body cited this entry. A frequency signal only -- a reference '
  'cited once in the methods can matter more than one cited eight times while '
  'positioning the work.';

COMMENT ON COLUMN item_references.contexts IS
  'Array of {section, sentence}: where each citation occurred and the sentence '
  'that made it.';

CREATE INDEX item_references_item_idx ON item_references (item_id);

-- Partial, because the unresolved half would otherwise dominate an index whose
-- only use is joining resolved entries to papers we hold.
CREATE INDEX item_references_doi_idx ON item_references (doi)
  WHERE doi IS NOT NULL;
CREATE INDEX item_references_arxiv_idx ON item_references (arxiv_id)
  WHERE arxiv_id IS NOT NULL;

-- The ingestion queue reads this: entries many documents lean on, ordered by
-- how load-bearing they are, restricted to what we have not already fetched.
CREATE INDEX item_references_ranking_idx ON item_references (mentions DESC)
  WHERE doi IS NOT NULL OR arxiv_id IS NOT NULL;

INSERT INTO schema_migrations (version) VALUES ('0010_item_references');

COMMIT;
