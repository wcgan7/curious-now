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
_FIGURE_LABEL = re.compile(r"^\s*((?:figure|fig\.?|table)\s*\d+[.:]?)", re.I)

# LaTeXML also wraps \paragraph{} units in section.ltx_paragraph. Those are too
# fine-grained to emit as sections, so their prose belongs to the enclosing
# section and their titles are kept inline as the lead-ins they are.
_BLOCK_SELECTOR = (
    "p.ltx_p, li.ltx_item, blockquote.ltx_quote, div.ltx_theorem,"
    " [class~=ltx_title_paragraph]"
)
_EMITTED_SECTION_CLASSES = frozenset(
    {"ltx_section", "ltx_subsection", "ltx_appendix"}
)


def _is_emitted_section(tag: Tag) -> bool:
    return tag.name == "section" and bool(
        _EMITTED_SECTION_CLASSES.intersection(tag.get("class") or ())
    )


def _compact(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _resolve_math(soup: BeautifulSoup) -> None:
    """Replace each math element with a single textual form.

    LaTeXML nests both a rendered form and the original TeX inside <math>, so
    reading the element's text yields "α \\alpha". Preferring the TeX keeps the
    notation faithful and avoids that duplication.
    """

    for node in soup.find_all("math"):
        tex = node.get("alttext")
        if not tex:
            annotation = node.find(
                "annotation", attrs={"encoding": "application/x-tex"}
            )
            tex = annotation.get_text() if annotation else None
        replacement = f" {_compact(tex)} " if tex else " "
        node.replace_with(replacement)


def _strip_noise(soup: BeautifulSoup) -> None:
    # Appendices are deliberately kept: they carry notation tables, ablations,
    # and architecture detail that a Technical walkthrough may need to cite.
    for selector in (
        "script",
        "style",
        ".ltx_bibliography",
        ".ltx_pagination",
        ".ltx_tag_section",
        ".ltx_tag_subsection",
        ".ltx_authors",
        ".ltx_role_affiliation",
    ):
        for node in soup.select(selector):
            node.decompose()


def _heading_of(node: Tag) -> str | None:
    heading = node.find(["h1", "h2", "h3", "h4", "h5", "h6"], recursive=False)
    if heading is None:
        heading = node.find(
            ["h1", "h2", "h3", "h4", "h5", "h6"],
            class_=lambda value: bool(value) and "ltx_title" in value,
        )
    return _compact(heading.get_text(" ")) if heading else None


def _paragraphs_of(node: Tag) -> tuple[str, ...]:
    """Direct prose of a section, excluding text owned by nested subsections."""

    # Keep a block only when this node is its nearest *emitted* section, so a
    # subsection owns its prose, the parent does not repeat it, and
    # ltx_paragraph wrappers do not swallow it.
    owned = [
        block
        for block in node.select(_BLOCK_SELECTOR)
        if block.find_parent(_is_emitted_section) is node
    ]
    # List items wrap their own <p>, so both match the selector and the text
    # would be collected twice. Keep only the outermost of any nested pair.
    owned_ids = {id(block) for block in owned}

    collected: list[str] = []
    for block in owned:
        if any(id(ancestor) in owned_ids for ancestor in block.parents):
            continue
        text = _compact(block.get_text(" "))
        if len(text) > 1:
            collected.append(text)
    return tuple(collected)


def _split_label(caption: str) -> tuple[str | None, str]:
    match = _FIGURE_LABEL.match(caption)
    if not match:
        return None, caption
    label = match.group(1).rstrip(".:").strip()
    return label, caption[match.end() :].strip(" .:")


def _captions(soup: BeautifulSoup) -> tuple[tuple[Figure, ...], tuple[Table, ...]]:
    """Collect one entry per citable figure or table.

    A multi-panel figure nests one <figure> per panel, each captioned "(a)",
    "(b)" and so on. Those are not separate figures — a reader cites "Figure 4",
    not "(b)" — so panel captions are folded into their parent.
    """

    figures: list[Figure] = []
    tables: list[Table] = []
    for node in soup.select("figure.ltx_figure, figure.ltx_table"):
        if node.find_parent("figure") is not None:
            continue

        captions = node.select(".ltx_caption")
        own = [c for c in captions if c.find_parent("figure") is node]
        if not own:
            continue
        label, caption = _split_label(_compact(own[0].get_text(" ")))
        if not caption:
            continue

        panels = [
            _compact(c.get_text(" "))
            for c in captions
            if c.find_parent("figure") is not node
        ]
        if panels:
            caption = f"{caption} Panels: {'; '.join(panels)}"

        if "ltx_table" in (node.get("class") or []):
            grid = node.find("table")
            tables.append(
                Table(
                    label=label,
                    caption=caption,
                    body=_compact(grid.get_text(" ")) if grid else "",
                )
            )
        else:
            figures.append(Figure(label=label, caption=caption))
    return tuple(figures), tuple(tables)


def extract_arxiv_html(html: str) -> Document:
    """Extract structure from an arXiv LaTeXML HTML rendering.

    This is the highest-quality path available for arXiv papers: sections,
    figure captions, and the original TeX are all marked up, so none of it has
    to be inferred the way it would from a PDF.
    """

    soup = BeautifulSoup(html, "html.parser")
    _resolve_math(soup)
    _strip_noise(soup)

    title_node = soup.select_one("h1.ltx_title_document, h1.ltx_title")
    title = _compact(title_node.get_text(" ")) if title_node else None

    abstract_node = soup.select_one(".ltx_abstract")
    abstract = None
    if abstract_node is not None:
        for heading in abstract_node.select(".ltx_title_abstract"):
            heading.decompose()
        abstract = _compact(abstract_node.get_text(" ")) or None

    sections: list[Section] = []
    for node in soup.select(
        "section.ltx_section, section.ltx_subsection, section.ltx_appendix"
    ):
        heading = _heading_of(node)
        paragraphs = _paragraphs_of(node)
        if not paragraphs and not heading:
            continue
        classes = node.get("class") or []
        # Appendix material is citable but is not the paper's own methods
        # section, so it never satisfies the mechanism Explain requires.
        kind = (
            SectionKind.APPENDIX
            if "ltx_appendix" in classes
            else classify_section(heading)
        )
        sections.append(
            Section(
                title=heading,
                kind=kind,
                paragraphs=paragraphs,
                level=2 if "ltx_subsection" in classes else 1,
            )
        )

    figures, tables = _captions(soup)
    warnings: list[str] = []
    if not sections:
        warnings.append("no LaTeXML sections found")

    return Document(
        extraction_method="arxiv_latexml_html",
        title=title,
        abstract=abstract,
        sections=inherit_section_kinds(infer_method_sections(tuple(sections))),
        figures=figures,
        tables=tables,
        warnings=tuple(warnings),
    )
