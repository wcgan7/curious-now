from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from curious_now_v2.retrieval.document import (
    CitationContext,
    Document,
    Figure,
    Reference,
    Section,
    SectionKind,
    Table,
    classify_section,
    find_identifiers,
    infer_method_sections,
    inherit_section_kinds,
    split_sentences,
)

_WHITESPACE = re.compile(r"\s+")
_FIGURE_LABEL = re.compile(r"^\s*((?:figure|fig\.?|table)\s*\d+[.:]?)", re.I)

# LaTeXML also wraps \paragraph{} units in section.ltx_paragraph. Those are too
# fine-grained to emit as sections, so their prose belongs to the enclosing
# section and their titles are kept inline as the lead-ins they are.
# Display mathematics sits outside the paragraph flow, in its own table: a
# lone equation in table.ltx_equation, an aligned group in table.ltx_eqn_table.
# Neither is inside a p.ltx_p, so leaving them out of this selector silently
# dropped the mathematics from every paper — 128 of 141 display equations in
# one fixture, 88 of 98 in another — while the surrounding prose went on
# referring to "Equation 3". The TeX itself was never the problem: it is in
# each element's alttext and _resolve_math already prefers it.
_BLOCK_SELECTOR = (
    "p.ltx_p, li.ltx_item, blockquote.ltx_quote, div.ltx_theorem,"
    " table.ltx_equation, table.ltx_eqn_table,"
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


# LaTeXML knows exactly where a formula starts and ends; splicing its TeX into
# prose bare threw that away, and nothing downstream could recover it. A reader
# then has to guess whether "p\in(1,2]" after a comma is mathematics or a typo,
# and so does the model writing about it. Delimiting costs four characters and
# makes the boundary a fact rather than an inference.
def _delimited(tex: str) -> str:
    """Wrap recovered TeX so its extent survives into the prose."""

    body = _compact(tex).strip()
    if not body:
        return " "
    # Already delimited by the source: leave it exactly as it is.
    if body.startswith(("\\(", "\\[", "$")):
        return f" {body} "
    return f" \\({body}\\) "

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
        node.replace_with(_delimited(tex) if tex else " ")


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


def _section_kind_at(node: Tag) -> SectionKind:
    """The role of the section a node sits in.

    Where a citation appears is a signal about what it is for: a reference cited
    in the methods is a dependency almost by definition, where the same
    reference in the introduction may only be setting the scene.
    """

    owner = node.find_parent(_is_emitted_section)
    if owner is None:
        return SectionKind.OTHER
    if "ltx_appendix" in (owner.get("class") or []):
        return SectionKind.APPENDIX
    return classify_section(_heading_of(owner))


def _citation_contexts(
    soup: BeautifulSoup,
) -> dict[str, list[CitationContext]]:
    """Map each bibliography anchor to the sentences that cited it.

    LaTeXML links every in-text marker to its entry — <cite> wraps an <a>
    pointing at "#bib.bib12" — so the marker never has to be parsed or matched
    by number. That link is what makes the mapping exact rather than heuristic.
    """

    contexts: dict[str, list[CitationContext]] = {}
    # One text extraction per block, reused by every citation inside it.
    block_text: dict[int, str] = {}
    consumed: dict[int, int] = {}

    for cite in soup.select("cite.ltx_cite"):
        keys = [
            href.removeprefix("#")
            for anchor in cite.find_all("a", href=True)
            if (href := anchor["href"]).startswith("#bib")
        ]
        if not keys:
            continue

        block = cite.find_parent(
            lambda tag: tag.name in {"p", "li", "blockquote", "div"}
        )
        if block is None:
            continue

        text = block_text.setdefault(id(block), _compact(block.get_text(" ")))
        marker = _compact(cite.get_text(" "))
        # Advance past markers already matched so a paragraph citing the same
        # entry twice attributes each mention to its own sentence.
        start = text.find(marker, consumed.get(id(block), 0)) if marker else -1
        if start >= 0:
            consumed[id(block)] = start + len(marker)

        sentence = text
        if start >= 0:
            offset = 0
            for candidate in split_sentences(text):
                offset = text.find(candidate, offset)
                if offset <= start < offset + len(candidate):
                    sentence = candidate
                    break
                offset += len(candidate)

        kind = _section_kind_at(cite)
        for key in keys:
            contexts.setdefault(key, []).append(
                CitationContext(section=kind, sentence=sentence)
            )
    return contexts


def _references(soup: BeautifulSoup) -> tuple[Reference, ...]:
    """Read the bibliography before _strip_noise removes it."""

    bibliography = soup.select_one(".ltx_bibliography")
    if bibliography is None:
        return ()

    contexts = _citation_contexts(soup)
    references: list[Reference] = []
    for entry in bibliography.select(".ltx_bibitem"):
        key = entry.get("id")
        if not key:
            continue
        tag_node = entry.select_one(".ltx_tag_bibitem")
        label = _compact(tag_node.get_text(" ")) if tag_node else None
        text = _compact(entry.get_text(" "))
        # The tag repeats at the head of the entry text; it is the label, not
        # part of the citation string.
        if label and text.startswith(label):
            text = text[len(label) :].strip()
        hrefs = tuple(
            anchor["href"] for anchor in entry.find_all("a", href=True)
        )
        doi, arxiv_id = find_identifiers(text, hrefs)
        references.append(
            Reference(
                key=key,
                label=label,
                text=text,
                doi=doi,
                arxiv_id=arxiv_id,
                contexts=tuple(contexts.get(key, ())),
            )
        )
    return tuple(references)


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


def _captions(soup: BeautifulSoup, base_url: str | None = None) -> tuple[tuple[Figure, ...], tuple[Table, ...]]:
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
            figures.append(
                Figure(
                    label=label,
                    caption=caption,
                    image_url=_figure_image(owner, base_url),
                )
            )
    return tuple(figures), tuple(tables)


def _figure_image(owner: Tag, base_url: str | None) -> str | None:
    """Resolve a figure's image against the page it was fetched from.

    LaTeXML writes every src relative — "2607.26029v1/x1.png" — so without the
    request URL there is nothing to join it to. Some figures are inline SVG
    instead, a TikZ picture compiled into the page itself; those have no URL
    because they need none, and they are simply skipped here.

    The base must not end in a slash: arXiv serves /html/{id} without
    redirecting, and joining onto a trailing slash silently doubles the path.
    """

    if not base_url:
        return None
    image = owner.find("img")
    src = (image.get("src") or "").strip() if image else ""
    if not src:
        return None
    resolved = urljoin(base_url.rstrip("/"), src)
    return resolved if resolved.startswith(("http://", "https://")) else None


def extract_arxiv_html(html: str, base_url: str | None = None) -> Document:
    """Extract structure from an arXiv LaTeXML HTML rendering.

    This is the highest-quality path available for arXiv papers: sections,
    figure captions, and the original TeX are all marked up, so none of it has
    to be inferred the way it would from a PDF.
    """

    soup = BeautifulSoup(html, "html.parser")
    _resolve_math(soup)
    # Before _strip_noise, which decomposes .ltx_bibliography: the entries and
    # the in-text links to them both have to be read while they still exist.
    references = _references(soup)
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

    figures, tables = _captions(soup, base_url)
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
        references=references,
        warnings=tuple(warnings),
    )
