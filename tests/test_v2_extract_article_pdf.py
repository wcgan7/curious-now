from __future__ import annotations

import re

import pytest

from curious_now_v2.core.enums import ExplanationDepth
from curious_now_v2.retrieval.document import SectionKind
from curious_now_v2.retrieval.extract_article import extract_article
from curious_now_v2.retrieval.extract_arxiv import extract_arxiv_html
from curious_now_v2.retrieval.extract_pdf import extract_pdf
from curious_now_v2.retrieval.quality import TextVerdict, assess_text
from tests.fixtures.loader import fixture_bytes, fixture_text, fixtures_of_kind

ARTICLE_FIXTURES = fixtures_of_kind(
    "news_html",
    "blog_html",
    "institutional_html",
    "publisher_html",
    "biorxiv_html",
)
PDF_FIXTURES = fixtures_of_kind("pdf")

# Pages that legitimately serve a teaser rather than the article.
WALLED = {"nature_article_html", "statnews_html"}


# --- article HTML -----------------------------------------------------------


@pytest.mark.parametrize("name", ARTICLE_FIXTURES)
def test_every_article_extracts_without_warnings(name: str) -> None:
    document = extract_article(fixture_text(name))

    assert document.warnings == ()
    assert document.title
    assert document.word_count > 0


@pytest.mark.parametrize(
    "name", [n for n in ARTICLE_FIXTURES if n not in WALLED]
)
def test_unwalled_articles_yield_usable_prose(name: str) -> None:
    document = extract_article(fixture_text(name))

    assert assess_text(document.text).verdict is TextVerdict.USABLE


@pytest.mark.parametrize("name", sorted(WALLED))
def test_walled_articles_are_still_recognised_after_extraction(name: str) -> None:
    """Extraction succeeds; the page itself is walled."""

    document = extract_article(fixture_text(name))

    assert assess_text(document.text).verdict is TextVerdict.SOFT_PAYWALL


def test_article_drops_trailing_related_links() -> None:
    """"More BBC stories on elephants" is furniture, not the article."""

    document = extract_article(fixture_text("bbc_news_html"))
    lowered = document.text.casefold()

    assert "more bbc stories" not in lowered


def test_article_does_not_use_meta_description_as_an_abstract() -> None:
    """A page's meta description repeats its opening paragraph, so treating it
    as an abstract would count the same prose twice."""

    for name in ("esa_press_html", "nvidia_blog_html"):
        document = extract_article(fixture_text(name))
        if document.abstract:
            assert document.abstract not in document.body_text


def test_preprint_landing_page_is_abstract_only() -> None:
    """medRxiv serves an abstract and declarations, never the full text, so it
    can ground a Glance but never an Explain."""

    document = extract_article(fixture_text("medrxiv_article_html"))
    assessment = assess_text(document.text, has_structure=document.has_structure)

    assert document.abstract
    assert len(document.abstract.split()) > 200
    assert document.sections == ()
    assert assessment.supported_depths == (ExplanationDepth.GLANCE,)


def test_article_headings_become_sections() -> None:
    document = extract_article(fixture_text("quanta_news_html"))

    assert len(document.sections) > 1
    assert any(section.title for section in document.sections)


def test_no_section_is_titled_the_headline() -> None:
    """Publishers repeat the headline as a heading. A page <title> may still be
    a prefix of the body's H1 — ScienceAlert's differ — so this checks for a
    section carrying the headline, not for the words appearing anywhere."""

    for name in ARTICLE_FIXTURES:
        document = extract_article(fixture_text(name))
        if not document.title:
            continue
        assert all(
            section.title != document.title for section in document.sections
        )


def test_unparseable_html_warns_rather_than_raising() -> None:
    document = extract_article("<html><body></body></html>")

    assert document.warnings
    assert document.sections == ()


# --- PDF --------------------------------------------------------------------


@pytest.mark.parametrize("name", PDF_FIXTURES)
def test_pdf_extracts_structure(name: str) -> None:
    document = extract_pdf(fixture_bytes(name))

    assert document.warnings == ()
    assert document.title
    assert document.has_structure
    assert document.word_count > 2000


@pytest.mark.parametrize("name", PDF_FIXTURES)
def test_pdf_headings_survive_body_size_faces(name: str) -> None:
    """AMS sets headings in small caps and REVTeX in bold-extended, both at
    body size — neither a larger face nor "bold" in the font name finds them,
    so a single sample made heading detection look far better than it was.

    Three, not more: the physics and maths fixtures are trimmed to four pages
    to stay versionable, and a four-page excerpt carries few real headings. An
    earlier threshold of four passed only because equations and axis ticks
    were being counted as sections.
    """

    document = extract_pdf(fixture_bytes(name))
    titled = [section for section in document.sections if section.title]

    assert len(titled) >= 3


@pytest.mark.parametrize("name", PDF_FIXTURES)
def test_pdf_abstract_is_prose_or_absent(name: str) -> None:
    """A cover page carries "Abstract word count: 353 words", which is a note
    about the abstract rather than the abstract."""

    document = extract_pdf(fixture_bytes(name))

    if document.abstract:
        assert len(document.abstract.split()) >= 50
        assert "word count" not in document.abstract.casefold()


@pytest.mark.parametrize("name", PDF_FIXTURES)
def test_pdf_carries_no_control_characters(name: str) -> None:
    document = extract_pdf(fixture_bytes(name))

    assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", document.text)


@pytest.mark.parametrize("name", PDF_FIXTURES)
def test_pdf_drops_preprint_server_stamps(name: str) -> None:
    """Preprint servers stamp every page with licence furniture."""

    lowered = extract_pdf(fixture_bytes(name)).text.casefold()

    for stamp in ("cc-by", "international license", "made available under"):
        assert stamp not in lowered


@pytest.mark.parametrize("name", PDF_FIXTURES)
def test_pdf_title_is_the_paper_not_the_journal(name: str) -> None:
    """Journals print a masthead above the title and repeat it as a running
    head, set larger than anything else — so size alone picks "PLOS ONE"."""

    document = extract_pdf(fixture_bytes(name))

    assert document.title
    assert len(document.title.split()) >= 4
    assert document.title.casefold() not in {"plos one", "nature", "science"}


@pytest.mark.parametrize("name", PDF_FIXTURES)
def test_pdf_drops_repeated_page_furniture(name: str) -> None:
    """A line printed on most pages is a running head, not prose."""

    document = extract_pdf(fixture_bytes(name))
    short_lines = [
        paragraph
        for section in document.sections
        for paragraph in section.paragraphs
        if len(paragraph) <= 120
    ]
    repeats = {
        line for line in short_lines if short_lines.count(line) >= 3
    }

    assert not repeats


def test_pdf_title_drops_the_article_type_label() -> None:
    document = extract_pdf(fixture_bytes("pdf_plos_typeset"))

    assert document.title
    assert not document.title.upper().startswith("RESEARCH ARTICLE")


def test_pdf_abstract_is_never_an_affiliation_list() -> None:
    """Affiliations sit exactly where an unlabelled abstract does."""

    for name in PDF_FIXTURES:
        document = extract_pdf(fixture_bytes(name))
        if not document.abstract:
            continue
        lowered = document.abstract.casefold()
        institutions = sum(
            lowered.count(word)
            for word in ("department", "university", "faculty")
        )
        assert institutions < 2


def test_numbered_affiliations_are_not_read_as_headings() -> None:
    """"7. Pathologie DNA, Nieuwegein, The Netherlands" is an affiliation.
    Headings do not carry commas, which is what tells them apart."""

    document = extract_pdf(fixture_bytes("pdf_medrxiv"))
    titles = [section.title or "" for section in document.sections]

    assert not any("," in title for title in titles)


def test_pdf_recovers_sections_in_reading_order() -> None:
    """Two-column PDFs interleave blocks; a short heading set at the top of the
    right column has its centre near the page middle, which is why column
    assignment keys on the left edge instead."""

    document = extract_pdf(fixture_bytes("arxiv_paper_pdf"))
    numbered = [
        section.title
        for section in document.sections
        if section.title and section.title[0].isdigit()
    ]

    assert numbered == sorted(numbered, key=lambda t: int(t.split(".")[0]))


def test_pdf_separates_tables_from_figures() -> None:
    document = extract_pdf(fixture_bytes("arxiv_paper_pdf"))

    assert document.tables
    assert all(
        (table.label or "").lower().startswith("table") for table in document.tables
    )
    assert all(
        (figure.label or "").lower().startswith("figure")
        for figure in document.figures
    )


def test_pdf_does_not_mistake_cross_references_for_captions() -> None:
    """"Table 4 displays pairwise tests..." is prose. Reading it as a caption
    both invents a float and deletes the sentence from the body."""

    document = extract_pdf(fixture_bytes("arxiv_paper_pdf"))
    labels = [table.label for table in document.tables]

    assert len(labels) == len(set(labels))
    assert any(
        "displays pairwise" in paragraph
        for section in document.sections
        for paragraph in section.paragraphs
    )


def test_pdf_recovers_lettered_appendices() -> None:
    """Appendices are lettered, not numbered, and are set in a larger face
    without bold — so neither the numbered nor the bold rule catches them."""

    document = extract_pdf(fixture_bytes("arxiv_paper_pdf"))
    titles = [section.title or "" for section in document.sections]

    assert any(title.startswith("A.") for title in titles)


def test_corrupt_pdf_warns_rather_than_raising() -> None:
    document = extract_pdf(b"%PDF-1.4 truncated garbage")

    assert document.warnings
    assert document.sections == ()


# --- the same paper through both paths --------------------------------------


def test_pdf_and_latexml_agree_on_the_same_paper() -> None:
    """The strongest check available: two wholly independent paths over one
    paper should recover the same structure."""

    pdf = extract_pdf(fixture_bytes("arxiv_paper_pdf"))
    html = extract_arxiv_html(fixture_text("arxiv_pdf_twin_html"))

    assert pdf.title == html.title
    assert len(pdf.figures) == len(html.figures)
    assert len(pdf.tables) == len(html.tables)

    for kind in (
        SectionKind.INTRODUCTION,
        SectionKind.METHOD,
        SectionKind.RESULTS,
        SectionKind.CONCLUSION,
    ):
        from_pdf = sum(s.word_count for s in pdf.sections_of_kind(kind))
        from_html = sum(s.word_count for s in html.sections_of_kind(kind))
        assert from_pdf > 0 and from_html > 0
        # Within 25%: the paths differ in how they treat inline math and
        # captions, but neither may lose or invent a section's substance.
        assert abs(from_pdf - from_html) / max(from_pdf, from_html) < 0.25
