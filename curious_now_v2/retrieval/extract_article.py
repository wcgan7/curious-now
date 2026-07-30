from __future__ import annotations

import re

import trafilatura

from curious_now_v2.retrieval.document import (
    Document,
    Section,
    SectionKind,
    classify_section,
    inherit_section_kinds,
)

_WHITESPACE = re.compile(r"\s+")

# Trailing furniture that reads as a heading but is not part of the article.
_TRAILING_HEADINGS = re.compile(
    r"^\s*(more (bbc )?stories|related (stories|articles|reading)|read more"
    r"|references? (&|and) resources|share this|follow us|sign up"
    r"|competing interest|author declarations?|supplementary|acknowledg)",
    re.I,
)

# Blocks that carry no prose.
_SKIP_TAGS = frozenset({"graphic", "table", "lb", "comments"})

# Consent and navigation furniture that survives body extraction on some sites
# and would otherwise be handed to generation as article text.
_FURNITURE = re.compile(
    r"accept all cookies|cookie (policy|settings|preferences)"
    r"|we use cookies|manage (your )?(cookies|preferences)"
    r"|skip to (main )?content|enable javascript|javascript is disabled"
    r"|sign up for our newsletter|subscribe to our newsletter",
    re.I,
)
# A client-side redirect page: the body is the notice, not the article.
_REDIRECT_STUB = re.compile(
    r"^\s*redirecting( to|\.\.\.)|you should be redirected automatically", re.I
)


def _compact(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _element_text(element: object) -> str:
    from lxml import etree

    return _compact(etree.tostring(element, method="text", encoding="unicode"))


def extract_article(html: str) -> Document:
    """Extract a news article, lab post, or institutional page.

    Web articles carry far less structure than papers: many have no headings
    at all, and those that do use them for narrative beats rather than the
    method/results roles a paper marks out. Sections are recovered where they
    exist and left unclassified where the headings say nothing, which keeps
    Technical correctly out of reach for ordinary journalism.
    """

    parsed = trafilatura.bare_extraction(
        html,
        with_metadata=True,
        favor_recall=True,
        include_comments=False,
        include_tables=False,
    )
    # bare_extraction is typed as returning a Document or a plain dict; only
    # the Document form carries the parsed body this extractor needs.
    if parsed is None or isinstance(parsed, dict) or parsed.body is None:
        return Document(
            extraction_method="article_html",
            warnings=("trafilatura recovered no article body",),
        )

    title = _compact(parsed.title) if parsed.title else None
    # Publishers append their own name to the page title. Strip it only when it
    # matches the site's declared name, so a headline that genuinely contains a
    # dash or pipe survives.
    sitename = _compact(parsed.sitename) if parsed.sitename else None
    if title and sitename:
        for separator in (" | ", " : ", " — ", " – ", " - "):
            head, found, tail = title.rpartition(separator)
            # Some sites append their tagline after the name, so match the
            # start of the trailing segment rather than the whole title.
            if found and head and tail.casefold().startswith(sitename.casefold()):
                title = head.strip()
                break

    sections: list[Section] = []
    heading: str | None = None
    paragraphs: list[str] = []
    dropped_trailing = False

    def flush() -> None:
        if not paragraphs and heading is None:
            return
        sections.append(
            Section(
                title=heading,
                kind=classify_section(heading),
                paragraphs=tuple(paragraphs),
            )
        )

    for element in parsed.body:
        tag = str(element.tag)
        if tag in _SKIP_TAGS:
            continue
        text = _element_text(element)
        if not text or _FURNITURE.search(text):
            continue

        if tag == "head":
            # Publishers repeat the headline as a heading, sometimes after a
            # kicker like "RESEARCH HIGHLIGHT". No section is legitimately
            # titled the article's own headline.
            if text == title:
                continue
            if _TRAILING_HEADINGS.match(text):
                # Related-links and declarations blocks trail the article.
                dropped_trailing = True
                break
            flush()
            heading, paragraphs = text, []
        else:
            paragraphs.append(text)

    if not dropped_trailing or paragraphs or heading is not None:
        flush()

    warnings: list[str] = []
    if not sections:
        warnings.append("no article prose recovered")
    elif _REDIRECT_STUB.match(sections[0].text or ""):
        # The page is a redirect notice; its target is a different URL.
        sections = []
        warnings.append("page is a client-side redirect, not an article")

    # A real abstract appears as a heading in the body — preprint landing pages
    # carry one. A page's meta description is search-engine copy that repeats
    # the opening paragraph, so it is deliberately not used here.
    abstract: str | None = None
    for index, section in enumerate(sections):
        if section.kind is SectionKind.ABSTRACT:
            abstract = section.text or None
            sections.pop(index)
            break

    return Document(
        extraction_method="article_html",
        title=title,
        abstract=abstract,
        sections=inherit_section_kinds(tuple(sections)),
        warnings=tuple(warnings),
    )


def article_has_prose(document: Document) -> bool:
    """Whether anything usable came back, before quality is assessed."""

    return bool(document.sections) and document.word_count > 0


__all__ = ["article_has_prose", "extract_article", "SectionKind"]
