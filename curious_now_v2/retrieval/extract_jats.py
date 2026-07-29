from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from curious_now_v2.retrieval.document import (
    Document,
    Figure,
    Section,
    SectionKind,
    Table,
    classify_section,
    infer_method_sections,
    inherit_section_kinds,
)

_WHITESPACE = re.compile(r"\s+")

# Marked up separately in JATS; keeping them inline would interleave caption and
# table text with the surrounding prose.
_PULLED_OUT = ("fig", "table-wrap", "supplementary-material")


def _compact(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _nearest_section(tag: Tag) -> Tag | None:
    return tag.find_parent("sec")


def _paragraphs_of(section: Tag) -> tuple[str, ...]:
    collected: list[str] = []
    for node in section.find_all("p"):
        # A <p> inside a nested <sec> belongs to that nested section.
        if _nearest_section(node) is not section:
            continue
        if node.find_parent(_PULLED_OUT) is not None:
            continue
        text = _compact(node.get_text(" "))
        if len(text) > 1:
            collected.append(text)
    return tuple(collected)


def _depth_of(section: Tag) -> int:
    depth = 1
    parent = section.find_parent("sec")
    while parent is not None:
        depth += 1
        parent = parent.find_parent("sec")
    return depth


def _in_translation(tag: Tag) -> bool:
    """Whether a node belongs to a <sub-article> translation or peer review.

    Bilingual journals ship the same figure twice, labelled "Figura 1" and
    "Figure 1". Sections are read from the main article's body, so floats must
    come from there too or the two disagree.
    """

    return tag.find_parent("sub-article") is not None


def _figures_and_tables(
    root: Tag,
) -> tuple[tuple[Figure, ...], tuple[Table, ...]]:
    figures: list[Figure] = []
    for node in root.find_all("fig"):
        if _in_translation(node):
            continue
        caption_node = node.find("caption")
        caption = _compact(caption_node.get_text(" ")) if caption_node else ""
        if not caption:
            continue
        label_node = node.find("label")
        figures.append(
            Figure(
                label=_compact(label_node.get_text()) if label_node else None,
                caption=caption,
            )
        )

    tables: list[Table] = []
    for node in root.find_all("table-wrap"):
        if _in_translation(node):
            continue
        label_node = node.find("label")
        caption_node = node.find("caption")
        grid = node.find("table")
        tables.append(
            Table(
                label=_compact(label_node.get_text()) if label_node else None,
                caption=(
                    _compact(caption_node.get_text(" ")) if caption_node else None
                ),
                body=_compact(grid.get_text(" ")) if grid else "",
            )
        )
    return tuple(figures), tuple(tables)


def extract_jats(xml: str) -> Document:
    """Extract structure from a JATS full-text XML article.

    PubMed Central and Europe PMC publish full text as JATS, where sections,
    figure captions, and tables are already marked up. Nothing has to be
    inferred from layout, so this is the most reliable path for the biomedical
    literature.
    """

    soup = BeautifulSoup(xml, "xml")

    title_node = soup.find("article-title")
    title = _compact(title_node.get_text(" ")) if title_node else None

    abstract_node = soup.find("abstract")
    abstract = None
    if abstract_node is not None:
        for label in abstract_node.find_all("title"):
            label.decompose()
        abstract = _compact(abstract_node.get_text(" ")) or None

    body = soup.find("body")
    sections: list[Section] = []
    if body is not None:
        for node in body.find_all("sec"):
            title_tag = node.find("title", recursive=False)
            heading = _compact(title_tag.get_text(" ")) if title_tag else None
            paragraphs = _paragraphs_of(node)
            if not paragraphs and not heading:
                continue
            sections.append(
                Section(
                    title=heading,
                    kind=classify_section(heading),
                    paragraphs=paragraphs,
                    level=_depth_of(node),
                )
            )

        if not sections:
            # Sectionless articles are valid JATS — book reviews, editorials,
            # and correspondence often place paragraphs straight in <body>.
            loose = tuple(
                text
                for node in body.find_all("p")
                if node.find_parent(_PULLED_OUT) is None
                and node.find_parent("sec") is None
                and len(text := _compact(node.get_text(" "))) > 1
            )
            if loose:
                sections.append(
                    Section(title=None, kind=SectionKind.OTHER, paragraphs=loose)
                )

    # Publishers place floats differently: some inline them in <body>, others
    # (MDPI among them) collect them in a <floats-group> beside it. Searching
    # the whole article catches both, plus any in back matter.
    figures, tables = _figures_and_tables(soup)

    warnings: list[str] = []
    if body is None:
        warnings.append("no <body> element; front matter only")
    elif not sections:
        warnings.append("no <sec> elements found")

    return Document(
        extraction_method="jats_xml",
        title=title,
        abstract=abstract,
        sections=inherit_section_kinds(infer_method_sections(tuple(sections))),
        figures=figures,
        tables=tables,
        warnings=tuple(warnings),
    )
