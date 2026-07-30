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
# Symbol-font math extracts one character per token, so a subscripted
# expression lands mid-paragraph as "k i k i" or "e r c". Prose does not run
# three bare letters together — "a" and "I" are the only single-letter English
# words — so such a run is mangled notation, and passing it on would hand
# generation something that looks like mathematics and states nothing.
_GLYPH_RUN = re.compile(r"(?<![\w-])((?:[a-z] ){2,}[a-z])(?![\w-])", re.I)
# "a" and "I" are the only single-letter English words, so a run carrying two
# or more letters that are neither is notation rather than prose. Excluding "i"
# from the pattern outright would miss the commonest case of all, since maths
# indexes with i, j and k.
_REAL_SINGLE_WORDS = frozenset("ai")


def _strip_glyph_runs(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        letters = match.group(1).split()
        notation = sum(1 for c in letters if c.casefold() not in _REAL_SINGLE_WORDS)
        return "[expression]" if notation >= 2 else match.group(0)

    return _GLYPH_RUN.sub(replace, text)
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

# Journals set an article-type label immediately above the title, and it ends
# up in the same block.
_TITLE_LABEL = re.compile(
    r"^\s*(research article|original research|review article|short report"
    r"|brief communication|perspective|editorial|letter|article)\s+(?=\S)",
    re.I,
)

# Math set in a PDF's symbol fonts extracts as single characters — an equation
# becomes "e e e e e e f f f f f f". Keeping it would hand generation something
# that looks like mathematics and says nothing.
def _is_glyph_soup(text: str) -> bool:
    tokens = text.split()
    if len(tokens) < 6:
        return False
    singles = sum(1 for token in tokens if len(token) == 1)
    return singles / len(tokens) > 0.5


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
    # After whitespace is normalised, not before: the letters of a mangled
    # expression arrive separated by newlines, which the run pattern would miss.
    return _strip_glyph_runs(_compact(text))


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
                or _is_glyph_soup(text)
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


def _drop_running_heads(blocks: list[_Block]) -> list[_Block]:
    """Remove the furniture repeated on every page.

    Journals print the masthead, article title, or a citation line in the
    header or footer of each page. It reads as ordinary text and, being short
    and near the top, is otherwise mistaken for the paper's title — a PLOS
    article extracted as "PLOS ONE".
    """

    pages = {block.page for block in blocks}
    if len(pages) < 3:
        return blocks

    appearances: dict[str, set[int]] = {}
    for block in blocks:
        if len(block.text) <= 120:
            appearances.setdefault(block.text, set()).add(block.page)

    repeated = {
        text for text, seen in appearances.items() if len(seen) >= 3
    }
    # Keep the first occurrence: a paper's own title is also printed as its
    # running head, and dropping every copy would lose the title itself.
    kept: list[_Block] = []
    seen_once: set[str] = set()
    for block in blocks:
        if block.text in repeated:
            if block.text in seen_once:
                continue
            seen_once.add(block.text)
        kept.append(block)
    return kept


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


def _looks_like_affiliations(text: str) -> bool:
    """Author affiliations sit exactly where an unlabelled abstract does.

    They are a comma-heavy list of institutions rather than prose, so they are
    told apart by density of institution words and commas per sentence.
    """

    lowered = text.casefold()
    institutions = sum(
        lowered.count(word)
        for word in ("department", "university", "faculty", "institute", "hospital")
    )
    sentences = max(text.count(". "), 1)
    return institutions >= 2 and text.count(",") / sentences > 3


_REAL_WORD = re.compile(r"[A-Za-z]{3,}")
# "1 Introduction 1" is a contents line; the trailing number is the page.
_TRAILING_PAGE = re.compile(r"\s+\d{1,3}\s*$")


def _reads_as_heading(text: str) -> bool:
    """Whether a line could name a section at all.

    A numbered line is not enough on its own. Axis ticks read as
    "4 6 8 10 12 14 16", and a displayed equation reads as
    "2 c1(V)2 -Tr(F2 ^F2) . (2.3)" — both match a numbered heading and neither
    names anything.
    """

    if not _REAL_WORD.search(text):
        return False
    tokens = text.split()
    numeric = sum(1 for token in tokens if not _REAL_WORD.search(token))
    return numeric <= len(tokens) / 2


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
    if not _reads_as_heading(block.text):
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
            blocks = _order_blocks(_drop_running_heads(_collect_blocks(pdf)))
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

    # A masthead such as "PLOS ONE" is set larger than anything else on the
    # page, so size alone would pick the journal over the paper.
    title = None
    candidates = [
        block for block in blocks[:8] if len(block.text.split()) >= 4
    ]
    largest = max(candidates, key=lambda b: b.size, default=None)
    if largest is not None and largest.size > body_size:
        title = _TITLE_LABEL.sub("", largest.text)
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
            # A contents page repeats every heading with its page number
            # appended, which would otherwise double the section list.
            heading, paragraphs = _TRAILING_PAGE.sub("", block.text), []
            continue
        if len(block.text.split()) < 4:
            continue
        paragraphs.append(block.text)

    flush()

    # A contents page lists every heading with no prose beneath it. Drop such a
    # listing in favour of the real section, but only when it is clearly the
    # listing: a structured abstract legitimately repeats "Methods" above a
    # body section of the same name, and both carry content.
    seen_titles: Counter[str] = Counter(
        (section.title or "").casefold() for section in sections if section.title
    )
    richest: dict[str, int] = {}
    for section in sections:
        key = (section.title or "").casefold()
        if key:
            richest[key] = max(richest.get(key, 0), section.word_count)
    sections = [
        section
        for section in sections
        # Only a repeated title can be a contents listing. A parent section
        # legitimately carries no prose of its own when its subsections hold
        # it all, and must not be dropped for being short.
        if not section.title
        or seen_titles[(section.title or "").casefold()] < 2
        or section.word_count >= max(
            50, richest[(section.title or "").casefold()] // 4
        )
    ]

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
            (
                p
                for p in sections[0].paragraphs
                if len(p.split()) > 50 and not _looks_like_affiliations(p)
            ),
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
