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

    Nesting means two different things in LaTeXML, and the caption's label
    tells them apart. A multi-panel figure nests one <figure> per panel,
    captioned "(a)", "(b)" — a reader cites "Figure 4", not "(b)", so those
    fold into the parent. But LaTeX also places two independently numbered
    floats side by side in one wrapper, and "Figure 4" and "Figure 5" nested
    that way are two separate figures, not panels of anything.

    The label also decides figure versus table: a side-by-side wrapper marks
    its children as ltx_figure even when their captions read "Table 3".
    """

    labelled: list[tuple[Tag, str | None, str]] = []
    unlabelled: list[tuple[Tag, str]] = []
    for caption_node in soup.select(".ltx_caption"):
        owner = caption_node.find_parent("figure")
        if owner is None:
            continue
        text = _compact(caption_node.get_text(" "))
        label, caption = _split_label(text)
        if label and caption:
            labelled.append((owner, label, caption))
        elif text and owner.find_parent("figure") is None:
            # An unnumbered caption on a standalone float is still that
            # float's caption, not a panel of anything.
            labelled.append((owner, None, text))
        elif text:
            unlabelled.append((owner, text))

    owners = {id(owner): index for index, (owner, _, _) in enumerate(labelled)}
    panels: dict[int, list[str]] = {}
    for owner, text in unlabelled:
        # Attach a panel to the nearest enclosing float that is itself numbered.
        for ancestor in (owner, *owner.parents):
            if id(ancestor) in owners:
                panels.setdefault(owners[id(ancestor)], []).append(text)
                break

    figures: list[Figure] = []
    tables: list[Table] = []
    for index, (owner, label, caption) in enumerate(labelled):
        if index in panels:
            caption = f"{caption} Panels: {'; '.join(panels[index])}"
        is_table = (
            label.casefold().startswith("table")
            if label
            else "ltx_table" in (owner.get("class") or [])
        )
        if is_table:
            grid = owner.find("table")
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

    # Short notes often place their prose straight in the document with no
    # sectioning at all, so anything outside every section would be lost.
    # LaTeXML wraps the title and author block in .ltx_block, which is how
    # front matter is told apart from body prose sitting at the same depth.
    candidates = soup.select(_BLOCK_SELECTOR)
    candidate_ids = {id(block) for block in candidates}
    # Affiliations and licence notices sit at the same depth as body prose but
    # always precede the abstract, so document order separates them.
    order = {id(tag): index for index, tag in enumerate(soup.find_all(True))}
    front_matter_ends = (
        order.get(id(abstract_node), -1) if abstract_node is not None else -1
    )
    loose = tuple(
        text
        for block in candidates
        if block.find_parent(_is_emitted_section) is None
        and block.find_parent(class_="ltx_abstract") is None
        and block.find_parent(class_="ltx_block") is None
        and order.get(id(block), 0) > front_matter_ends
        and not any(id(ancestor) in candidate_ids for ancestor in block.parents)
        and (text := _compact(block.get_text(" "))) != title
        and len(text) > 1
    )
    if loose:
        sections.insert(
            0,
            Section(title=None, kind=SectionKind.OTHER, paragraphs=loose),
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
