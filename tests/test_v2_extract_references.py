from __future__ import annotations

import pytest

from curious_now_v2.retrieval.document import SectionKind, find_identifiers
from curious_now_v2.retrieval.extract_article import extract_article
from curious_now_v2.retrieval.extract_arxiv import extract_arxiv_html
from curious_now_v2.retrieval.extract_jats import extract_jats
from tests.fixtures.loader import fixture_text, fixtures_of_kind

ARXIV_FIXTURES = fixtures_of_kind("arxiv_html")
JATS_FIXTURES = fixtures_of_kind("jats_xml")


@pytest.fixture(scope="module")
def arxiv_doc():
    return extract_arxiv_html(fixture_text("arxiv_latexml_html"))


# --- identifiers ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected_doi", "expected_arxiv"),
    [
        ("Smith. A paper. doi:10.1038/s41586-020-2649-2.", "10.1038/s41586-020-2649-2", None),
        ("Vaswani et al. arXiv:1706.03762", None, "1706.03762"),
        ("See https://arxiv.org/abs/2202.10793v2 for details", None, "2202.10793"),
        ("No identifiers in this entry at all.", None, None),
    ],
)
def test_identifiers_recovered_from_entry_text(
    text: str, expected_doi: str | None, expected_arxiv: str | None
) -> None:
    doi, arxiv_id = find_identifiers(text)
    assert doi == expected_doi
    assert arxiv_id == expected_arxiv


def test_doi_does_not_swallow_sentence_punctuation() -> None:
    """A DOI ending a citation must not absorb the full stop that closed it."""

    doi, _ = find_identifiers("Published at 10.1371/journal.pbio.3003908.")
    assert doi == "10.1371/journal.pbio.3003908"


def test_link_identifier_wins_over_prose() -> None:
    """The publisher's own href is unambiguous where quoted prose may not be."""

    doi, _ = find_identifiers(
        "reanalysis of the dataset 10.5281/zenodo.999999",
        ("https://doi.org/10.1038/nature12373",),
    )
    assert doi == "10.1038/nature12373"


# --- arXiv ------------------------------------------------------------------


def test_arxiv_recovers_bibliography(arxiv_doc) -> None:
    assert arxiv_doc.references, "no references recovered from a LaTeXML paper"
    assert len({ref.key for ref in arxiv_doc.references}) == len(
        arxiv_doc.references
    ), "bibliography keys are not unique"


def test_arxiv_links_markers_to_entries(arxiv_doc) -> None:
    """The <cite> anchors make this exact, so most entries should be reached."""

    cited = [ref for ref in arxiv_doc.references if ref.mentions]
    assert len(cited) > len(arxiv_doc.references) // 2


def test_every_context_carries_a_sentence(arxiv_doc) -> None:
    for ref in arxiv_doc.references:
        for context in ref.contexts:
            assert context.sentence.strip()
            assert isinstance(context.section, SectionKind)


@pytest.mark.parametrize("name", ARXIV_FIXTURES)
def test_references_never_leak_into_prose(name: str) -> None:
    """The bibliography must stay out of the text an explanation may draw on.

    Technical cites figures and sections by quoting them, so a reference list
    inside `text` would let a citation be satisfied by the bibliography rather
    than by the paper.
    """

    document = extract_arxiv_html(fixture_text(name))
    prose = document.text
    for ref in document.references[:25]:
        if len(ref.text) > 60:
            assert ref.text[:60] not in prose


@pytest.mark.parametrize("name", ARXIV_FIXTURES)
def test_arxiv_bibliography_survives_stripping(name: str) -> None:
    """_strip_noise removes .ltx_bibliography, so extraction must precede it."""

    document = extract_arxiv_html(fixture_text(name))
    html = fixture_text(name)
    if "ltx_bibitem" in html:
        assert document.references, f"{name} has bibitems but recovered none"


# --- JATS -------------------------------------------------------------------


@pytest.mark.parametrize("name", JATS_FIXTURES)
def test_jats_reads_back_matter_references(name: str) -> None:
    """<ref-list> lives in <back>, outside the <body> the section scan reads."""

    xml = fixture_text(name)
    document = extract_jats(xml)
    if "<ref " in xml or "<ref>" in xml:
        assert document.references, f"{name} has <ref> elements but recovered none"


@pytest.mark.parametrize("name", JATS_FIXTURES)
def test_jats_prefers_declared_identifiers(name: str) -> None:
    """JATS states DOIs in <pub-id>; those must not be re-derived from prose."""

    xml = fixture_text(name)
    document = extract_jats(xml)
    if 'pub-id-type="doi"' not in xml:
        pytest.skip("fixture declares no DOIs")
    assert any(ref.doi for ref in document.references)


# --- Springer Nature HTML ---------------------------------------------------


_SPRINGER_HTML = """
<html><body><article>
  <h1>A paper about mice</h1>
  <p>The trajectory depends on background<a href="#ref-CR1">1</a>.
     Later work disagreed<a href="/articles/s41586-1#ref-CR2">2</a>.
     We reuse that design<a href="#ref-CR1">1</a> throughout.</p>
  <ol class="c-article-references">
    <li class="c-article-references__item" data-counter="1.">
      <p class="c-article-references__text" id="ref-CR1">
        Aitken, S. J. et al. Pervasive lesion segregation. Nature 583, 265 (2020).</p>
      <p><a href="https://doi.org/10.1038%2Fs41586-020-2435-1">Article</a></p>
    </li>
    <li class="c-article-references__item" data-counter="2.">
      <p class="c-article-references__text" id="ref-CR2">
        Thomas, C. E. &amp; Peters, U. Genomic landscape. Nat. Rev. Genet. 26, 336 (2025).</p>
    </li>
  </ol>
</article></body></html>
"""


def test_springer_bibliography_is_read_from_raw_markup() -> None:
    """Trafilatura discards the reference list, so it is parsed separately."""

    document = extract_article(_SPRINGER_HTML)

    assert len(document.references) == 2
    assert [ref.label for ref in document.references] == ["1", "2"]


def test_springer_percent_encoded_doi_is_decoded() -> None:
    """Nature writes "10.1038%2Fs41586-..." — no DOI pattern matches that raw."""

    document = extract_article(_SPRINGER_HTML)
    first = document.references[0]

    assert first.doi == "10.1038/s41586-020-2435-1"


def test_springer_markers_link_by_fragment_not_whole_href() -> None:
    """The same page writes "#ref-CR3" and "/articles/xxx#ref-CR3"."""

    document = extract_article(_SPRINGER_HTML)
    by_key = {ref.key: ref for ref in document.references}

    assert by_key["ref-CR1"].mentions == 2
    assert by_key["ref-CR2"].mentions == 1
    assert "background" in by_key["ref-CR1"].contexts[0].sentence


def test_links_inside_the_bibliography_are_not_citations() -> None:
    """An "Article" link within an entry points at a reference but cites nothing."""

    document = extract_article(_SPRINGER_HTML)

    assert sum(ref.mentions for ref in document.references) == 3


def test_ordinary_journalism_yields_no_references() -> None:
    html = (
        "<html><body><article><h1>Sky is blue</h1>"
        + "<p>" + " ".join(f"word{n}" for n in range(400)) + "</p>"
        + "</article></body></html>"
    )

    assert extract_article(html).references == ()


# --- PDF --------------------------------------------------------------------


def test_pdf_entries_split_on_bracket_numbers() -> None:
    from curious_now_v2.retrieval.extract_pdf import _split_entries

    entries = _split_entries(
        "[1] Smith, J. A study of things. Journal 1, 1 (2020). "
        "[2] Jones, K. Another study entirely. Journal 2, 9 (2021)."
    )

    assert [number for number, _ in entries] == ["1", "2"]
    assert entries[0][1].startswith("Smith")


def test_pdf_unnumbered_block_is_one_entry() -> None:
    """PyMuPDF emits one block per entry, which author-year styles rely on."""

    from curious_now_v2.retrieval.extract_pdf import _split_entries

    entries = _split_entries(
        "Autio, C., Schwartz, R. and Roberts, K. Artificial intelligence risk. 2024."
    )

    assert len(entries) == 1
    assert entries[0][0] is None


def test_pdf_fragments_too_short_to_be_entries_are_dropped() -> None:
    from curious_now_v2.retrieval.extract_pdf import _split_entries

    assert _split_entries("ibid.") == []


@pytest.mark.parametrize("name", fixtures_of_kind("pdf"))
def test_pdf_references_never_leak_into_prose(name: str) -> None:
    """Whatever is recovered must stay out of the text an explanation reads."""

    import gzip

    from curious_now_v2.retrieval.extract_pdf import extract_pdf
    from tests.fixtures.loader import fixture_path

    raw = fixture_path(name).read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    document = extract_pdf(raw)

    for ref in document.references[:15]:
        if len(ref.text) > 60:
            assert ref.text[:60] not in document.text


def test_pdf_reference_keys_are_unique_when_numbering_is_mixed() -> None:
    """Keying by the printed number collides and aborts the item's whole write.

    A bibliography where entry 1 is labelled "5" and entry 5 is unlabelled has
    two references wanting "pdf-ref-5". Because the insert shares a transaction
    with the item's full text, that duplicate rolled back the text too.
    """

    from curious_now_v2.retrieval.document import Section, SectionKind
    from curious_now_v2.retrieval.extract_pdf import _pdf_references

    section = Section(
        title="References",
        kind=SectionKind.REFERENCES,
        paragraphs=(
            "5. Alpha, A. A first work of substance. Journal 1, 1 (2001).",
            "Beta, B. An unnumbered work of substance. Journal 2, 2 (2002).",
            "6. Gamma, C. A third work of substance. Journal 3, 3 (2003).",
            "Delta, D. Another unnumbered work entirely. Journal 4, 4 (2004).",
            "7. Epsilon, E. A fifth work of substance. Journal 5, 5 (2005).",
        ),
    )

    references = _pdf_references([section])
    keys = [reference.key for reference in references]

    assert len(keys) == len(set(keys)), f"duplicate reference keys: {keys}"
