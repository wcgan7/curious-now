from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace

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
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# "3 Methodology", "3.1. Preliminaries", or a bare word like "Abstract".
_NUMBERED_HEADING = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+\S")
# Physics journals number sections with Roman numerals: "I. INTRODUCTION".
_ROMAN_HEADING = re.compile(r"^\s*[IVXLC]{1,6}\.\s+\S")
_ABSTRACT_LEAD = re.compile(r"^\s*abstract\s*[.:—-]?\s+(?=\S)", re.I)

# TeX section headings are set in caps-and-small-caps (CMCSC) or bold-extended
# (CMBX) at body size, so neither a larger face nor the word "bold" in the
# font name identifies them.
_HEADING_FONTS = ("csc", "smallcap", "sc-", "bx", "bold", "medi", "semib", "black")
_BOLD_FLAG = 1 << 4
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
# Preprint servers stamp every page with licence and status furniture.
_STAMP = re.compile(
    r"cc-by|creative commons|international license|made available under"
    r"|is the author/funder|medrxiv preprint|biorxiv preprint"
    r"|not certified by peer review|doi:\s*https?://",
    re.I,
)
# Minimum length for something to be an abstract rather than a cover-page note
# such as "Abstract word count: 353 words".
MIN_ABSTRACT_WORDS = 50

MAX_PAGES = 60


@dataclass(frozen=True)
class _Block:
    text: str
    size: float
    page: int
    x_left: float
    width: float
    y_top: float
    emphasised: bool

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
    # PDF text layers carry stray control bytes that would otherwise travel
    # into an explanation.
    return _WHITESPACE.sub(" ", _CONTROL.sub("", value)).strip()


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
            if (
                not text
                or _PAGE_NUMBER.match(text)
                or _ARXIV_STAMP.match(text)
                or _STAMP.search(text[:160])
            ):
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
                    emphasised=any(
                        bool(int(span.get("flags", 0)) & _BOLD_FLAG)
                        or any(
                            marker in str(span.get("font", "")).casefold()
                            for marker in _HEADING_FONTS
                        )
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


def _heading_level(text: str) -> int:
    """Depth from the numbering: "4." is 1, "4.1." is 2, "3.2.1." is 3.

    Without this every heading sits at level 1, and a subsection cannot inherit
    its parent's role — "4.1 Goal language" would not be read as results.
    """

    match = re.match(r"^\s*(\d+(?:\.\d+)*)", text)
    if not match:
        return 1
    return min(match.group(1).count(".") + 1, 4)


def _is_heading(block: _Block, body_size: float) -> bool:
    if len(block.text) > 90 or "\n" in block.text:
        return False
    words = len(block.text.split())
    larger = block.size > body_size + 0.6
    marked = larger or block.emphasised
    numbered = _NUMBERED_HEADING.match(block.text) or _ROMAN_HEADING.match(block.text)

    if numbered and marked:
        return True
    # A short numbered line stands alone as a heading even when set at body
    # size in an unremarkable face, as AMS styles do. Numbered affiliation
    # lists look the same but always carry commas, which headings do not.
    if numbered and words <= 8 and "," not in block.text:
        return True
    if _BARE_HEADING.match(block.text) and marked:
        return True
    if _LETTER_HEADING.match(block.text) and larger and words <= 8:
        return True
    return marked and words <= 8 and block.text.upper() == block.text


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
    else:
        # AMS styles set the title at body size, so nothing stands out by face.
        # It is then the first short line on the opening page.
        title = next(
            (
                block.text
                for block in blocks[:4]
                if block.page == 0 and 2 <= len(block.text.split()) <= 20
            ),
            None,
        )

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
                    level=_heading_level(heading) if heading else 1,
                )
            )

    for block in blocks:
        if block.text == title:
            continue
        # Many styles run the abstract straight on from the word "Abstract"
        # rather than giving it a heading of its own.
        lead = _ABSTRACT_LEAD.match(block.text)
        if (
            lead
            and abstract is None
            and len(block.text.split()) >= MIN_ABSTRACT_WORDS
        ):
            abstract = block.text[lead.end() :]
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
    if abstract is None:
        for index, section in enumerate(sections):
            if section.kind is SectionKind.ABSTRACT:
                if len(section.text.split()) < MIN_ABSTRACT_WORDS:
                    # "Abstract word count: 353 words" is a cover-page note.
                    break
                abstract = section.text
                sections.pop(index)
                break

    if abstract is None and sections and sections[0].title is None:
        # Physics styles print the abstract with no label at all, between the
        # affiliations and the first numbered section. It is the substantial
        # paragraph in that unheaded run.
        candidate = max(
            (p for p in sections[0].paragraphs if len(p.split()) > 50),
            key=lambda p: len(p.split()),
            default=None,
        )
        if candidate is not None:
            abstract = candidate
            remaining = tuple(
                p for p in sections[0].paragraphs if p != candidate
            )
            if remaining:
                sections[0] = replace(sections[0], paragraphs=remaining)
            else:
                sections.pop(0)

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
