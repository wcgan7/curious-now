from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import fitz

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
# "3 Methodology", "3.1. Preliminaries", or a bare word like "Abstract".
_NUMBERED_HEADING = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+\S")
_BARE_HEADING = re.compile(
    r"^\s*(abstract|introduction|background|related work|method\w*|materials"
    r"|results?|discussion|conclusions?|limitations?|references|acknowledg\w*"
    r"|appendix)\b",
    re.I,
)
# The separator is required. Without it "Table 4 displays pairwise tests..."
# — an ordinary cross-reference in the prose — reads as a caption, which both
# invents a float and deletes the sentence from the body.
# Appendices are lettered rather than numbered: "A. Prompt examples".
_LETTER_HEADING = re.compile(r"^\s*(?:appendix\s+)?[A-Z][.):]\s+[A-Z]")
_CAPTION = re.compile(r"^\s*((?:figure|fig\.?|table)\s*\d+)\s*[.:]\s+(\S.*)", re.I)
# Hyphen at a line break, but not a real compound.
_LINE_HYPHEN = re.compile(r"(\w)-\n(\w)")
_PAGE_NUMBER = re.compile(r"^\s*\d{1,3}\s*$")
_ARXIV_STAMP = re.compile(r"^\s*arxiv:\s*\d", re.I)

MAX_PAGES = 60


@dataclass(frozen=True)
class _Block:
    text: str
    size: float
    page: int
    x_left: float
    width: float
    y_top: float
    bold: bool

    @property
    def spans_page(self) -> bool:
        """A full-width block sits across both columns."""

        return self.width > 0.6

    @property
    def in_right_column(self) -> bool:
        # Keyed on the left edge, not the centre: a short heading like
        # "3. Methods" set at the top of the right column has its centre near
        # the page middle and would otherwise read as full-width.
        return self.x_left >= 0.45


def _compact(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _reflow(text: str) -> str:
    """Rejoin lines broken by layout, keeping real compounds intact."""

    text = _LINE_HYPHEN.sub(r"\1\2", text)
    return _compact(text)


def _collect_blocks(document: fitz.Document) -> list[_Block]:
    blocks: list[_Block] = []
    for index, page in enumerate(document):
        if index >= MAX_PAGES:
            break
        width = page.rect.width or 1.0
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            spans = [
                span
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            ]
            if not spans:
                continue
            text = _reflow(
                "\n".join(
                    "".join(span["text"] for span in line.get("spans", []))
                    for line in block.get("lines", [])
                )
            )
            if not text or _PAGE_NUMBER.match(text) or _ARXIV_STAMP.match(text):
                continue
            sizes = Counter(round(span["size"], 1) for span in spans)
            bbox = block.get("bbox", (0, 0, 0, 0))
            blocks.append(
                _Block(
                    text=text,
                    size=sizes.most_common(1)[0][0],
                    page=index,
                    x_left=bbox[0] / width,
                    width=(bbox[2] - bbox[0]) / width,
                    y_top=bbox[1],
                    bold=any(
                        "bold" in str(span.get("font", "")).casefold()
                        for span in spans
                    ),
                )
            )
    return blocks


def _order_blocks(blocks: list[_Block]) -> list[_Block]:
    """Sort into reading order, handling two-column layouts.

    Academic PDFs store blocks in creation order, which interleaves columns.
    A page is treated as two-column when blocks cluster to either side of the
    midline; otherwise the original top-to-bottom order stands.
    """

    ordered: list[_Block] = []
    for page in sorted({block.page for block in blocks}):
        page_blocks = sorted(
            (block for block in blocks if block.page == page),
            key=lambda block: block.y_top,
        )
        spanning = [block for block in page_blocks if block.spans_page]
        columned = [block for block in page_blocks if not block.spans_page]
        left = [block for block in columned if not block.in_right_column]
        right = [block for block in columned if block.in_right_column]

        if len(left) >= 2 and len(right) >= 2:
            # Full-width blocks are almost always the title and abstract at the
            # head of the page, so they lead; then each column top to bottom.
            ordered.extend(spanning)
            ordered.extend(left)
            ordered.extend(right)
        else:
            ordered.extend(page_blocks)
    return ordered


def _is_heading(block: _Block, body_size: float) -> bool:
    if len(block.text) > 90 or "\n" in block.text:
        return False
    larger = block.size > body_size + 0.6
    if _NUMBERED_HEADING.match(block.text) and (larger or block.bold):
        return True
    if _BARE_HEADING.match(block.text) and (larger or block.bold):
        return True
    if _LETTER_HEADING.match(block.text) and larger and len(block.text.split()) <= 8:
        return True
    return larger and block.bold and len(block.text.split()) <= 8


def extract_pdf(data: bytes) -> Document:
    """Extract a paper from PDF, the last-resort path.

    A PDF records glyph positions, not structure, so sections and captions are
    inferred from font size and layout rather than read from markup. Every
    structured source is preferred over this one.
    """

    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                return Document(
                    extraction_method="pdf",
                    warnings=("PDF is password protected",),
                )
            blocks = _order_blocks(_collect_blocks(pdf))
    except Exception as exc:  # noqa: BLE001 - a malformed PDF is data, not a bug
        return Document(
            extraction_method="pdf",
            warnings=(f"PDF could not be parsed: {type(exc).__name__}",),
        )

    if not blocks:
        return Document(
            extraction_method="pdf",
            warnings=("no text layer; the PDF is probably scanned",),
        )

    weights: Counter[float] = Counter()
    for block in blocks:
        weights[block.size] += len(block.text)
    body_size = weights.most_common(1)[0][0]

    title = None
    largest = max(blocks[:6], key=lambda b: b.size, default=None)
    if largest is not None and largest.size > body_size:
        title = largest.text

    figures: list[Figure] = []
    tables: list[Table] = []
    sections: list[Section] = []
    heading: str | None = None
    paragraphs: list[str] = []
    abstract: str | None = None

    def flush() -> None:
        if paragraphs or heading is not None:
            sections.append(
                Section(
                    title=heading,
                    kind=classify_section(heading),
                    paragraphs=tuple(paragraphs),
                )
            )

    for block in blocks:
        if block.text == title:
            continue
        caption = _CAPTION.match(block.text)
        if caption:
            label = _compact(caption.group(1))
            body = _compact(caption.group(2))
            if label.casefold().startswith("table"):
                tables.append(Table(label=label, caption=body))
            else:
                figures.append(Figure(label=label, caption=body))
            continue
        if _is_heading(block, body_size):
            flush()
            heading, paragraphs = block.text, []
            continue
        if len(block.text.split()) < 4:
            continue
        paragraphs.append(block.text)

    flush()

    # The abstract is a section in the text, but belongs in its own field.
    for index, section in enumerate(sections):
        if section.kind is SectionKind.ABSTRACT:
            abstract = section.text or None
            sections.pop(index)
            break

    warnings: list[str] = []
    if not sections:
        warnings.append("no sections recovered from the PDF")

    return Document(
        extraction_method="pdf",
        title=title,
        abstract=abstract,
        sections=inherit_section_kinds(infer_method_sections(tuple(sections))),
        figures=tuple(figures),
        tables=tuple(tables),
        warnings=tuple(warnings),
    )
