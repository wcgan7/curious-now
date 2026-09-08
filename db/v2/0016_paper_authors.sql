-- Who wrote the papers we already read.
--
-- The corpus holds 72 papers citing Fei-Fei Li and no record that they do,
-- because hydration asks arXiv and Crossref for an abstract and discards the
-- rest of the same response. The author list arrives in those bytes already
-- paid for; nothing was stopping us keeping it except that nothing asked.
--
-- Stored verbatim, per provider, with no canonical author entity behind it.
-- The concept experiment is the reason: a canonical name invented by us is a
-- claim we cannot support, and "L. Fei-Fei", "Fei-Fei, L." and "Li Fei-Fei"
-- are the same disambiguation problem that made 95% of generated concept names
-- singletons. ORCID is the exception -- it is a global identifier the provider
-- asserts rather than one we infer -- which is why it gets its own index and a
-- name does not.
--
-- Position is kept because author order carries meaning in most fields: the
-- first and last names on a paper are not two of six equal contributors.
--
-- affiliation is nullable and expected to be mostly null. Crossref returned an
-- empty affiliation array for every author of the Nature Communications paper
-- checked before writing this, and arXiv's optional affiliation element is
-- rarely populated. Where an author works is OpenAlex's `authorships`, not
-- Crossref's -- this table records who, and deliberately does not pretend to
-- record where.

BEGIN;

CREATE TABLE paper_authors (
  paper_id UUID NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
  -- Zero-based, in the order the provider listed them.
  position INTEGER NOT NULL CHECK (position >= 0),
  -- Always present. arXiv gives one display string and no split, so this is
  -- the only field both providers can fill.
  full_name TEXT NOT NULL CHECK (length(btrim(full_name)) > 0),
  family TEXT NULL,
  given TEXT NULL,
  orcid TEXT NULL,
  affiliation TEXT NULL,
  -- Which provider said so, matching papers.metadata->>'extraction_method'.
  source TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (paper_id, position)
);

COMMENT ON TABLE paper_authors IS
  'Author lists as the hydration provider gave them. No canonical author '
  'identity is asserted; ORCID is the only trustworthy join key.';

-- The identity that can be followed. Partial, because most rows have none.
CREATE INDEX paper_authors_orcid_idx
  ON paper_authors (orcid)
  WHERE orcid IS NOT NULL;

-- Ranking authors by how much of the corpus cites them reads by surname, since
-- that is the part a bibliography always prints and an initial never loses.
CREATE INDEX paper_authors_family_idx
  ON paper_authors (lower(family))
  WHERE family IS NOT NULL;

INSERT INTO schema_migrations (version) VALUES ('0016_paper_authors');

COMMIT;
