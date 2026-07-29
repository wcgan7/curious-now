from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from curious_now_v2.retrieval.document import (
    Section,
    SectionKind,
    classify_section,
    inherit_section_kinds,
)
from curious_now_v2.retrieval.extract_arxiv import extract_arxiv_html
from curious_now_v2.retrieval.extract_jats import extract_jats
from tests.fixtures.loader import fixture_text, fixtures_of_kind

ARXIV_FIXTURES = fixtures_of_kind("arxiv_html")
JATS_FIXTURES = fixtures_of_kind("jats_xml")


@pytest.fixture(scope="module")
def arxiv_doc():
    return extract_arxiv_html(fixture_text("arxiv_latexml_html"))


@pytest.fixture(scope="module")
def jats_doc():
    return extract_jats(fixture_text("pmc_jats_xml"))


# --- run across every captured paper, not just one --------------------------


@pytest.mark.parametrize("name", ARXIV_FIXTURES)
def test_every_arxiv_paper_recovers_all_citable_floats(name: str) -> None:
    """A single sample hid two real losses; every captured paper is counted."""

    raw = fixture_text(name)
    document = extract_arxiv_html(raw)
    soup = BeautifulSoup(raw, "html.parser")
    citable = [
        node
        for node in soup.select("figure.ltx_figure, figure.ltx_table")
        if node.find_parent("figure") is None
    ]

    assert len(document.figures) + len(document.tables) == len(citable)


@pytest.mark.parametrize("name", JATS_FIXTURES)
def test_every_jats_article_recovers_all_floats(name: str) -> None:
    """Publishers place floats in <body> or in a sibling <floats-group>."""

    raw = fixture_text(name)
    document = extract_jats(raw)
    soup = BeautifulSoup(raw, "xml")

    assert len(document.figures) == len(soup.find_all("fig"))
    assert len(document.tables) == len(soup.find_all("table-wrap"))


@pytest.mark.parametrize("name", [*ARXIV_FIXTURES, *JATS_FIXTURES])
def test_every_structured_paper_extracts_cleanly(name: str) -> None:
    extract = extract_arxiv_html if name in ARXIV_FIXTURES else extract_jats
    document = extract(fixture_text(name))

    assert document.warnings == ()
    assert document.title
    assert document.sections
    assert document.has_structure
    assert document.word_count > 500


@pytest.mark.parametrize("name", [*ARXIV_FIXTURES, *JATS_FIXTURES])
def test_a_section_never_repeats_its_own_prose(name: str) -> None:
    """List items wrap their own paragraph, so both match the block selector
    and the text would otherwise be collected twice."""

    extract = extract_arxiv_html if name in ARXIV_FIXTURES else extract_jats
    document = extract(fixture_text(name))

    for section in document.sections:
        substantial = [
            paragraph
            for paragraph in section.paragraphs
            if len(paragraph.split()) > 10
        ]
        assert len(substantial) == len(set(substantial))


@pytest.mark.parametrize("name", [*ARXIV_FIXTURES, *JATS_FIXTURES])
def test_a_parent_section_never_repeats_a_child_section(name: str) -> None:
    """Ownership must resolve to the nearest section.

    Papers do legitimately repeat themselves between distant sections — a
    data-availability statement restated in an appendix, for instance — so this
    checks the ancestor chain rather than the whole document.
    """

    extract = extract_arxiv_html if name in ARXIV_FIXTURES else extract_jats
    document = extract(fixture_text(name))

    ancestors: dict[int, Section] = {}
    for section in document.sections:
        for level in [key for key in ancestors if key >= section.level]:
            del ancestors[level]
        for ancestor in ancestors.values():
            overlap = set(section.paragraphs) & set(ancestor.paragraphs)
            assert not overlap, (
                f"{section.title!r} repeats prose from {ancestor.title!r}"
            )
        ancestors[section.level] = section


@pytest.mark.parametrize("name", ARXIV_FIXTURES)
def test_no_paper_leaks_duplicated_math(name: str) -> None:
    text = extract_arxiv_html(fixture_text(name)).text

    for rendered, tex in (("α", "\\alpha"), ("β", "\\beta"), ("↓", "\\downarrow")):
        assert f"{rendered} {tex}" not in text


# --- section classification -------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("3 Methodology", SectionKind.METHOD),
        ("Materials and methods", SectionKind.METHOD),
        ("4 Experimental Setup", SectionKind.METHOD),
        ("2 Related Work", SectionKind.RELATED_WORK),
        ("5 Results", SectionKind.RESULTS),
        ("Results and discussion", SectionKind.RESULTS),
        ("Limitations", SectionKind.LIMITATIONS),
        ("6 Conclusion", SectionKind.CONCLUSION),
        ("1 Introduction", SectionKind.INTRODUCTION),
        ("References", SectionKind.REFERENCES),
        ("3.1. Preliminaries", SectionKind.OTHER),
        (None, SectionKind.OTHER),
    ],
)
def test_headings_map_to_their_role(title: str | None, expected: SectionKind) -> None:
    assert classify_section(title) is expected


def test_related_work_is_not_mistaken_for_results() -> None:
    """"Related Work" contains "work", and "Results and discussion" contains
    "discussion"; the more specific rule must win in both cases."""

    assert classify_section("Related Work") is SectionKind.RELATED_WORK
    assert classify_section("Results and discussion") is SectionKind.RESULTS


def test_unclassified_subsections_inherit_the_enclosing_role() -> None:
    sections = (
        Section(title="Methodology", kind=SectionKind.METHOD, level=1),
        Section(title="Preliminaries", kind=SectionKind.OTHER, level=2),
        Section(title="Results", kind=SectionKind.RESULTS, level=1),
        Section(title="Ablations", kind=SectionKind.OTHER, level=2),
    )

    resolved = inherit_section_kinds(sections)

    assert [section.kind for section in resolved] == [
        SectionKind.METHOD,
        SectionKind.METHOD,
        SectionKind.RESULTS,
        SectionKind.RESULTS,
    ]


def test_inheritance_does_not_leak_across_siblings() -> None:
    """A top-level section after a classified one keeps its own role."""

    sections = (
        Section(title="Methods", kind=SectionKind.METHOD, level=1),
        Section(title="Something unlabelled", kind=SectionKind.OTHER, level=1),
    )

    assert inherit_section_kinds(sections)[1].kind is SectionKind.OTHER


# --- arXiv LaTeXML ----------------------------------------------------------


def test_arxiv_recovers_title_abstract_and_sections(arxiv_doc) -> None:
    assert arxiv_doc.title is not None
    assert arxiv_doc.abstract is not None
    assert not arxiv_doc.abstract.lower().startswith("abstract")
    assert arxiv_doc.has_structure
    assert arxiv_doc.warnings == ()


def test_arxiv_recovers_the_method_section(arxiv_doc) -> None:
    """Explain requires mechanism, so the method section is load-bearing."""

    assert arxiv_doc.has_method_section
    method_words = sum(
        section.word_count
        for section in arxiv_doc.sections_of_kind(SectionKind.METHOD)
    )
    assert method_words > 500


def test_arxiv_recovers_limitations_prose(arxiv_doc) -> None:
    limitations = arxiv_doc.sections_of_kind(SectionKind.LIMITATIONS)

    assert limitations
    assert limitations[0].word_count > 50


def test_arxiv_keeps_prose_nested_below_subsections(arxiv_doc) -> None:
    """LaTeXML nests \\paragraph units in their own <section>; that prose must
    be attributed to the enclosing section rather than dropped."""

    assert arxiv_doc.word_count > 4000


def test_arxiv_attributes_prose_to_exactly_one_section(arxiv_doc) -> None:
    """A subsection owns its prose; the parent must not repeat it."""

    body = arxiv_doc.body_text
    sample = arxiv_doc.sections_of_kind(SectionKind.LIMITATIONS)[0].paragraphs[-1]

    assert body.count(sample) == 1


def test_arxiv_math_is_not_duplicated(arxiv_doc) -> None:
    """LaTeXML nests a rendered form and the TeX inside <math>; reading both
    yields "α \\alpha". Only the TeX should survive."""

    assert "α \\alpha" not in arxiv_doc.text
    assert "\\alpha" in arxiv_doc.text or "\\downarrow" in arxiv_doc.text


def test_arxiv_keeps_figure_captions(arxiv_doc) -> None:
    assert arxiv_doc.figures
    first = arxiv_doc.figures[0]
    assert first.label is not None
    assert first.label.lower().startswith("figure")
    assert len(first.caption.split()) > 5


def test_arxiv_keeps_table_captions(arxiv_doc) -> None:
    assert arxiv_doc.tables
    assert any(table.caption for table in arxiv_doc.tables)


def test_arxiv_recovers_every_citable_figure_and_table(arxiv_doc) -> None:
    """Count against the source, not against itself.

    Asserting only that some captions were found hid two real losses: appendix
    figures were being stripped, and multi-panel sub-figures were inflating the
    count while their parent was still counted once.
    """

    soup = BeautifulSoup(fixture_text("arxiv_latexml_html"), "html.parser")
    citable = [
        node
        for node in soup.select("figure.ltx_figure, figure.ltx_table")
        if node.find_parent("figure") is None
    ]
    expected_tables = sum(
        1 for node in citable if "ltx_table" in (node.get("class") or [])
    )

    assert len(arxiv_doc.figures) + len(arxiv_doc.tables) == len(citable)
    assert len(arxiv_doc.tables) == expected_tables


def test_arxiv_figure_numbering_has_no_gaps(arxiv_doc) -> None:
    numbers = [
        int(figure.label.split()[-1])
        for figure in arxiv_doc.figures
        if figure.label and figure.label.split()[-1].isdigit()
    ]

    assert numbers == list(range(1, len(numbers) + 1))


def test_arxiv_folds_panel_captions_into_their_parent(arxiv_doc) -> None:
    """A reader cites "Figure 4", never "(b)", so panels are not figures."""

    panelled = [
        figure for figure in arxiv_doc.figures if "Panels:" in figure.caption
    ]

    assert panelled
    assert "(a)" in panelled[0].caption
    assert not any(
        figure.caption.startswith("(") for figure in arxiv_doc.figures
    )


def test_arxiv_keeps_appendix_content(arxiv_doc) -> None:
    """Appendices carry notation tables, ablations, and architecture detail
    that a Technical walkthrough may need to cite."""

    appendix = arxiv_doc.sections_of_kind(SectionKind.APPENDIX)

    assert appendix
    assert sum(section.word_count for section in appendix) > 100
    assert any(
        table.caption and "notation" in table.caption.lower()
        for table in arxiv_doc.tables
    )


def test_appendix_never_satisfies_the_mechanism_requirement(arxiv_doc) -> None:
    """Appendix method detail is citable but is not the paper's own methods
    section, so it must not stand in for the mechanism Explain requires."""

    method_titles = [
        section.title for section in arxiv_doc.sections_of_kind(SectionKind.METHOD)
    ]

    assert not any(
        (title or "").lower().startswith("appendix") for title in method_titles
    )


def test_arxiv_excludes_references_from_body_text(arxiv_doc) -> None:
    body = arxiv_doc.body_text

    assert "bibliography" not in body.lower()


def test_malformed_arxiv_html_yields_a_warning_not_a_crash() -> None:
    document = extract_arxiv_html("<html><body><p>no sections here</p></body></html>")

    assert document.sections == ()
    assert "no LaTeXML sections found" in document.warnings


# --- JATS -------------------------------------------------------------------


def test_jats_recovers_title_abstract_and_sections(jats_doc) -> None:
    assert jats_doc.title is not None
    assert jats_doc.abstract is not None
    assert jats_doc.has_structure
    assert jats_doc.warnings == ()


def test_jats_recovers_the_method_section(jats_doc) -> None:
    assert jats_doc.has_method_section
    titles = [
        section.title
        for section in jats_doc.sections_of_kind(SectionKind.METHOD)
    ]
    assert "Materials and methods" in titles
    # Nested analysis subsections are method content by inheritance.
    assert "Statistical analyses" in titles


def test_jats_keeps_table_labels_and_captions(jats_doc) -> None:
    assert jats_doc.tables
    labelled = [table for table in jats_doc.tables if table.label]
    assert labelled
    assert labelled[0].label.lower().startswith("table")
    assert labelled[0].caption


def test_jats_recovers_every_figure_and_table(jats_doc) -> None:
    soup = BeautifulSoup(fixture_text("pmc_jats_xml"), "xml")

    # table-wrap-foot is a footnote block inside a table, not another table.
    assert len(jats_doc.tables) == len(soup.find_all("table-wrap"))
    assert len(jats_doc.figures) == len(soup.find_all("fig"))


def test_jats_attributes_prose_to_exactly_one_section(jats_doc) -> None:
    body = jats_doc.body_text
    sample = jats_doc.sections_of_kind(SectionKind.RESULTS)[0].paragraphs[0]

    assert body.count(sample) == 1


def test_jats_without_a_body_warns_instead_of_failing() -> None:
    document = extract_jats(
        "<article><front><article-meta>"
        "<title-group><article-title>Only front matter</article-title></title-group>"
        "</article-meta></front></article>"
    )

    assert document.title == "Only front matter"
    assert document.sections == ()
    assert "no <body> element; front matter only" in document.warnings


def test_both_extractors_produce_enough_text_for_the_deep_layers(
    arxiv_doc,
    jats_doc,
) -> None:
    """Structured sources should clear the Technical word floor comfortably."""

    for document in (arxiv_doc, jats_doc):
        assert document.word_count > 2000
        assert document.has_structure
