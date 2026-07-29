#!/usr/bin/env python
"""Audit extraction across every captured fixture.

Runs a battery of invariants over each structured document and reports
violations. Intended for iterative hardening: capture more fixtures, run this,
fix what it finds, repeat until a round comes back clean.

    python scripts/v2_extraction_audit.py [--verbose]

Exits non-zero if any check FAILs. WARN marks something worth a look that is
not necessarily wrong (a review article legitimately has no methods section).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass

from bs4 import BeautifulSoup

from curious_now_v2.retrieval.document import Document
from curious_now_v2.retrieval.extract_article import extract_article
from curious_now_v2.retrieval.extract_arxiv import extract_arxiv_html
from curious_now_v2.retrieval.extract_jats import extract_jats
from curious_now_v2.retrieval.extract_pdf import extract_pdf
from curious_now_v2.retrieval.quality import TextVerdict, assess_text
from tests.fixtures.loader import fixture_bytes, fixture_text, fixtures_of_kind

PASS, WARN, FAIL = "pass", "warn", "fail"

# Navigation and consent furniture that must never reach an explanation.
BOILERPLATE = (
    "skip to main content",
    "accept all cookies",
    "cookie policy",
    "sign up for our newsletter",
    "share on twitter",
    "advertisement",
    "javascript is disabled",
    "enable javascript",
)

# The closing bracket is required: mathematical prose says "0<a<b<1", which
# otherwise reads as an anchor tag.
_HTML_TAG = re.compile(
    r"<\s*/?\s*(?:div|span|p|a|img|script|table|tr|td|br)(?:\s[^<>]*)?\s*/?>",
    re.I,
)
_ENTITY = re.compile(r"&(?:amp|lt|gt|quot|nbsp|#\d+);")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MOJIBAKE = re.compile(r"â€[™œ\x9d“”]|Ã[©¨¡³±¼\x83]|ï»¿|Â[\xa0§°]")
_CITABLE_LABEL = re.compile(r"^\s*(?:figure|fig\.?|table)\s*\d+", re.I)


@dataclass
class Finding:
    status: str
    detail: str = ""


Check = Callable[[Document, str, str], Finding]


def ok() -> Finding:
    return Finding(PASS)


def check_no_warnings(doc: Document, raw: str, kind: str) -> Finding:
    return Finding(FAIL, "; ".join(doc.warnings)) if doc.warnings else ok()


def check_title(doc: Document, raw: str, kind: str) -> Finding:
    return ok() if doc.title else Finding(FAIL, "no title")


def check_abstract(doc: Document, raw: str, kind: str) -> Finding:
    if doc.abstract or kind == "article_html":
        return ok()
    return Finding(WARN, "no abstract recovered")


# Below this nothing can be grounded at all; between it and SHORT_DOC a
# document is a note or review rather than a broken extraction.
GROUNDABLE_WORDS = 150
SHORT_DOC_WORDS = 500


def check_structure(doc: Document, raw: str, kind: str) -> Finding:
    if not doc.sections:
        # A preprint landing page serves an abstract and nothing else. That is
        # a real access class, not a failure to read the page.
        if doc.abstract:
            return Finding(WARN, "abstract only; no body served")
        return Finding(FAIL, "no sections")
    if not doc.has_structure:
        # News and blog posts use headings for narrative beats, not the
        # method/results roles a paper marks out; unclassified is correct.
        if kind == "article_html":
            return ok()
        # Book reviews, correspondence, and short notes carry little or no
        # sectioning. Failing to classify a *substantial, sectioned* document
        # is a bug; an article that simply has no sections is its shape.
        if len(doc.sections) == 1 and doc.sections[0].title is None:
            return Finding(WARN, "sectionless article")
        if doc.word_count < SHORT_DOC_WORDS:
            return Finding(WARN, f"unsectioned {doc.word_count}-word note")
        return Finding(FAIL, "no section classified")
    return ok()


def check_word_floor(doc: Document, raw: str, kind: str) -> Finding:
    if doc.word_count < GROUNDABLE_WORDS:
        # A publisher serving a teaser under HTTP 200 is correctly extracted;
        # the page is walled, the extractor is not broken.
        if assess_text(doc.text).verdict is TextVerdict.SOFT_PAYWALL:
            return Finding(WARN, f"soft paywall: {doc.word_count} words served")
        return Finding(FAIL, f"only {doc.word_count} words")
    if doc.word_count < SHORT_DOC_WORDS:
        return Finding(WARN, f"short document: {doc.word_count} words")
    return ok()


def check_floats_complete(doc: Document, raw: str, kind: str) -> Finding:
    # Only markup declares its floats. A PDF's are inferred from captions and
    # an article rarely has any, so there is nothing to count against.
    if kind not in {"arxiv_html", "jats_xml"}:
        return ok()
    got = len(doc.figures) + len(doc.tables)
    if kind == "arxiv_html":
        # Count captions a reader could cite. Top-level <figure> nodes are the
        # wrong unit: LaTeX places two numbered floats in one side-by-side
        # wrapper, and panels of one figure each get their own <figure>.
        soup = BeautifulSoup(raw, "html.parser")
        expected = len(
            [
                node
                for node in soup.select(".ltx_caption")
                if node.find_parent("figure") is not None
                and (
                    _CITABLE_LABEL.match(node.get_text(" ", strip=True))
                    or node.find_parent("figure").find_parent("figure") is None
                )
            ]
        )
    else:
        soup = BeautifulSoup(raw, "xml")
        # Translations in <sub-article> repeat every float; the main article
        # is the one the sections come from.
        expected = len(
            [
                node
                for node in soup.find_all(["fig", "table-wrap"])
                if node.find_parent("sub-article") is None
            ]
        )
    if got != expected:
        return Finding(FAIL, f"recovered {got} of {expected}")
    return ok()


def check_empty_section_ratio(doc: Document, raw: str, kind: str) -> Finding:
    """A high share of wordless sections points at broken prose attribution."""

    if not doc.sections:
        return ok() if doc.abstract else Finding(FAIL, "no sections")
    empty = sum(1 for section in doc.sections if section.word_count == 0)
    ratio = empty / len(doc.sections)
    if ratio > 0.6:
        return Finding(FAIL, f"{empty}/{len(doc.sections)} sections empty")
    if ratio > 0.4:
        return Finding(WARN, f"{empty}/{len(doc.sections)} sections empty")
    return ok()


def check_intra_section_duplication(doc: Document, raw: str, kind: str) -> Finding:
    for section in doc.sections:
        substantial = [p for p in section.paragraphs if len(p.split()) > 10]
        if len(substantial) == len(set(substantial)):
            continue
        # Markup nests a paragraph inside its list item, so a repeat there is
        # the extractor's doing. A PDF's blocks are physical and disjoint, so a
        # repeat is the paper reprinting something — a prompt template, say.
        detail = f"{section.title!r} repeats its own prose"
        return Finding(WARN if kind == "pdf" else FAIL, detail)
    return ok()


def check_ancestor_duplication(doc: Document, raw: str, kind: str) -> Finding:
    ancestors: dict[int, object] = {}
    for section in doc.sections:
        for level in [key for key in ancestors if key >= section.level]:
            del ancestors[level]
        for ancestor in ancestors.values():
            overlap = set(section.paragraphs) & set(ancestor.paragraphs)  # type: ignore[attr-defined]
            if overlap:
                return Finding(FAIL, f"{section.title!r} repeats its parent")
        ancestors[section.level] = section
    return ok()


def check_math_not_duplicated(doc: Document, raw: str, kind: str) -> Finding:
    if kind != "arxiv_html":
        return ok()
    text = doc.text
    for rendered, tex in (("α", "\\alpha"), ("β", "\\beta"), ("↓", "\\downarrow")):
        if f"{rendered} {tex}" in text:
            return Finding(FAIL, f"math rendered twice: {rendered} {tex}")
    return ok()


def check_no_markup_leakage(doc: Document, raw: str, kind: str) -> Finding:
    text = doc.text
    tag = _HTML_TAG.search(text)
    if tag:
        return Finding(FAIL, f"markup in text: {text[tag.start():tag.start()+40]!r}")
    entity = _ENTITY.search(text)
    if entity:
        return Finding(FAIL, f"unescaped entity: {entity.group()}")
    if _CONTROL.search(text):
        return Finding(FAIL, "control characters in text")
    return ok()


def check_no_boilerplate(doc: Document, raw: str, kind: str) -> Finding:
    lowered = doc.text.casefold()
    hits = [phrase for phrase in BOILERPLATE if phrase in lowered]
    if hits:
        return Finding(FAIL, f"boilerplate: {', '.join(hits[:2])}")
    return ok()


def check_abstract_not_repeated(doc: Document, raw: str, kind: str) -> Finding:
    """The abstract is stored separately; repeating it in the body inflates
    every downstream word count."""

    if not doc.abstract or len(doc.abstract.split()) < 30:
        return ok()
    probe = " ".join(doc.abstract.split()[:20])
    if probe in doc.body_text:
        return Finding(FAIL, "abstract repeated in body")
    return ok()


def check_no_mojibake(doc: Document, raw: str, kind: str) -> Finding:
    """UTF-8 read as Latin-1 leaves telltale sequences that would otherwise
    travel all the way into a generated explanation."""

    hit = _MOJIBAKE.search(doc.text)
    if hit:
        return Finding(FAIL, f"encoding damage near {hit.group()!r}")
    return ok()


def check_paragraph_not_merged(doc: Document, raw: str, kind: str) -> Finding:
    """One enormous paragraph means block boundaries were lost."""

    longest = max(
        (
            len(paragraph.split())
            for section in doc.sections
            for paragraph in section.paragraphs
        ),
        default=0,
    )
    if longest > 2000:
        return Finding(FAIL, f"single paragraph of {longest} words")
    if longest > 800:
        return Finding(WARN, f"long paragraph: {longest} words")
    return ok()


def check_title_not_body(doc: Document, raw: str, kind: str) -> Finding:
    """Front matter must not be collected as prose."""

    if not doc.title:
        return ok()
    for section in doc.sections:
        if any(paragraph == doc.title for paragraph in section.paragraphs):
            return Finding(FAIL, "title collected as body prose")
    return ok()


def check_headings_name_something(doc: Document, raw: str, kind: str) -> Finding:
    """A section title has to be words.

    Inferring headings from a PDF's geometry picks up displayed equations and
    axis tick rows — "4 6 8 10 12 14 16" matches a numbered heading and names
    nothing. Those become citation targets a Technical walkthrough would offer
    the reader, so they matter beyond tidiness.
    """

    titles = [section.title for section in doc.sections if section.title]
    if not titles:
        return ok()
    junk = [title for title in titles if not re.search(r"[A-Za-z]{3,}", title)]
    if junk:
        return Finding(FAIL, f"{len(junk)}/{len(titles)} name nothing: {junk[:2]}")
    return ok()


def check_figure_numbering(doc: Document, raw: str, kind: str) -> Finding:
    numbers = [
        int(figure.label.split()[-1])
        for figure in doc.figures
        if figure.label and figure.label.split()[-1].isdigit()
    ]
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        return Finding(WARN, f"figure numbering {numbers}")
    return ok()


def check_paragraph_fragmentation(doc: Document, raw: str, kind: str) -> Finding:
    """Very short average paragraphs suggest prose split into fragments."""

    paragraphs = [p for section in doc.sections for p in section.paragraphs]
    if len(paragraphs) < 5:
        return ok()
    average = sum(len(p.split()) for p in paragraphs) / len(paragraphs)
    if average < 12:
        return Finding(WARN, f"mean paragraph {average:.0f} words")
    return ok()


def check_method_present(doc: Document, raw: str, kind: str) -> Finding:
    """Not a failure: reviews, editorials, and news carry no methodology."""

    if kind == "article_html" or doc.has_method_section:
        return ok()
    return Finding(WARN, "no method section")


CHECKS: tuple[tuple[str, Check], ...] = (
    ("warnings", check_no_warnings),
    ("title", check_title),
    ("abstract", check_abstract),
    ("structure", check_structure),
    ("words", check_word_floor),
    ("floats", check_floats_complete),
    ("empty-secs", check_empty_section_ratio),
    ("dup-self", check_intra_section_duplication),
    ("dup-parent", check_ancestor_duplication),
    ("math", check_math_not_duplicated),
    ("markup", check_no_markup_leakage),
    ("boilerplate", check_no_boilerplate),
    ("abstract-dup", check_abstract_not_repeated),
    ("mojibake", check_no_mojibake),
    ("merged-para", check_paragraph_not_merged),
    ("title-in-body", check_title_not_body),
    ("headings", check_headings_name_something),
    ("fig-numbers", check_figure_numbering),
    ("fragments", check_paragraph_fragmentation),
    ("method", check_method_present),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    kinds = (
        ("arxiv_html", ("arxiv_html",)),
        ("jats_xml", ("jats_xml",)),
        ("pdf", ("pdf",)),
        (
            "article_html",
            (
                "news_html",
                "blog_html",
                "institutional_html",
                "publisher_html",
                "biorxiv_html",
            ),
        ),
    )
    targets = [
        (name, label)
        for label, wanted in kinds
        for name in fixtures_of_kind(*wanted)
    ]

    failures = 0
    warnings = 0
    for name, kind in targets:
        try:
            if kind == "pdf":
                raw = ""
                document = extract_pdf(fixture_bytes(name))
            else:
                raw = fixture_text(name)
                document = {
                    "arxiv_html": extract_arxiv_html,
                    "jats_xml": extract_jats,
                    "article_html": extract_article,
                }[kind](raw)
        except Exception as exc:  # noqa: BLE001 - the audit reports, never raises
            print(f"FAIL {name}: extractor raised {type(exc).__name__}: {exc}")
            failures += 1
            continue

        problems = []
        for label, check in CHECKS:
            finding = check(document, raw, kind)
            if finding.status is PASS:
                continue
            problems.append((label, finding))
            if finding.status == FAIL:
                failures += 1
            else:
                warnings += 1

        flag = "FAIL" if any(f.status == FAIL for _, f in problems) else (
            "warn" if problems else "ok"
        )
        summary = (
            f"{document.word_count:>6,}w "
            f"{len(document.sections):>3d}sec "
            f"{len(document.figures) + len(document.tables):>3d}float"
        )
        print(f"[{flag:4s}] {name:26s} {summary}")
        for label, finding in problems:
            print(f"         {finding.status.upper():4s} {label:14s} {finding.detail}")
        if args.verbose:
            for section in document.sections:
                print(
                    f"           L{section.level} {section.kind.value:13s} "
                    f"{section.word_count:>5d}w  {(section.title or '')[:44]}"
                )

    print(
        f"\n{len(targets)} fixtures audited: {failures} failures, {warnings} warnings"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
