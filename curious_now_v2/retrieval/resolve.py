from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import quote, urlsplit, urlunsplit

from curious_now_v2.retrieval.document import Document, Reference
from curious_now_v2.retrieval.extract_article import extract_article
from curious_now_v2.retrieval.extract_arxiv import extract_arxiv_html
from curious_now_v2.retrieval.extract_jats import extract_jats
from curious_now_v2.retrieval.extract_pdf import extract_pdf
from curious_now_v2.retrieval.fetch import Fetcher, FetchOutcome
from curious_now_v2.retrieval.images import extract_html_preview_image
from curious_now_v2.retrieval.quality import TextVerdict, assess_text
from curious_now_v2.retrieval.select import (
    ScoredDocument,
    is_good_enough,
    pick_best,
    score_document,
)

EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPE_PMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
OPENALEX_WORK = "https://api.openalex.org/works/doi:{doi}"


class TextKind(StrEnum):
    FULL_TEXT = "fulltext"
    ABSTRACT = "abstract"


class ResolutionStatus(StrEnum):
    OK = "ok"
    PAYWALLED = "paywalled"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    ERROR = "error"


@dataclass(frozen=True)
class Candidate:
    """One way of obtaining an item's text, with how to read what comes back."""

    url: str
    source: str
    parser: str
    expected_kind: TextKind | None = None
    open_access: bool = True
    licence: str | None = None


@dataclass(frozen=True)
class RawFetch:
    """One response exactly as it arrived, before anything read it.

    Kept so that changing an extractor never again means asking a publisher for
    a page they already gave us.
    """

    source: str
    parser: str
    url: str
    body: bytes
    final_url: str | None = None
    status_code: int | None = None
    content_type: str | None = None


@dataclass(frozen=True)
class Resolution:
    """The text chosen for an item, and the bibliography found for it.

    `references` is separate from `document` because the two are not always
    best served by the same candidate. A short eLife or PLOS piece scores
    higher as publisher HTML than as JATS on prose, while only the JATS carries
    the reference list -- ten fully identified entries in the cases measured.
    Tying the bibliography to whichever candidate won on prose threw those away
    for no gain.
    """

    status: ResolutionStatus
    source: str | None = None
    kind: TextKind | None = None
    document: Document | None = None
    score: float = 0.0
    licence: str | None = None
    references: tuple[Reference, ...] = field(default_factory=tuple)
    reference_source: str | None = None
    fetches: tuple[RawFetch, ...] = field(default_factory=tuple)
    attempted: tuple[str, ...] = field(default_factory=tuple)
    reasons: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None
    image_url: str | None = None

    @property
    def text(self) -> str:
        return self.document.text if self.document else ""


def _europe_pmc_id(fetcher: Fetcher, doi: str) -> str | None:
    """Map a DOI to a PMC identifier, when the article is in Europe PMC."""

    result = fetcher.fetch(
        f'{EUROPE_PMC_SEARCH}?query=DOI:"{doi}"&format=json&pageSize=1',
        accept="application/json",
    )
    if not result.ok:
        return None
    try:
        payload = json.loads(result.text())
        entries = payload["resultList"]["result"]
    except (ValueError, KeyError, TypeError):
        return None
    for entry in entries:
        pmcid = entry.get("pmcid")
        if pmcid and entry.get("isOpenAccess") == "Y":
            return str(pmcid)
    return None


def _openalex_locations(fetcher: Fetcher, doi: str) -> tuple[Candidate, ...]:
    """Open-access copies OpenAlex knows about, best first."""

    result = fetcher.fetch(
        OPENALEX_WORK.format(doi=doi), accept="application/json"
    )
    if not result.ok:
        return ()
    try:
        payload = json.loads(result.text())
    except ValueError:
        return ()

    seen: set[str] = set()
    candidates: list[Candidate] = []
    locations = [payload.get("best_oa_location"), *(payload.get("locations") or [])]
    for location in locations:
        if not isinstance(location, dict) or not location.get("is_oa"):
            continue
        licence = location.get("license")
        for url, parser, source in (
            (location.get("pdf_url"), "pdf", "oa_pdf"),
            (location.get("landing_page_url"), "article", "publisher_html"),
        ):
            if not url or url in seen:
                continue
            seen.add(url)
            candidates.append(
                Candidate(
                    url=url,
                    source=source,
                    parser=parser,
                    expected_kind=(
                        TextKind.FULL_TEXT if parser == "pdf" else None
                    ),
                    licence=licence,
                )
            )
    return tuple(candidates)


# PLOS serves JATS per journal, keyed by the DOI's own infix.
_PLOS_JOURNALS = {
    "pbio": "plosbiology",
    "pmed": "plosmedicine",
    "pone": "plosone",
    "pgen": "plosgenetics",
    "pcbi": "ploscompbiol",
    "ppat": "plospathogens",
    "pntd": "plosntds",
    "pclm": "climate",
    "pwat": "water",
    "pdig": "digitalhealth",
    "pgph": "globalpublichealth",
    "pmen": "mentalhealth",
    "pstr": "sustainabilitytransformation",
}
_PLOS_DOI = re.compile(r"^10\.1371/journal\.([a-z]{4})\.", re.I)
_ELIFE_ARTICLE = re.compile(
    r"elifesciences\.org/(?:articles|reviewed-preprints)/(\d+)", re.I
)


_PREPRINT_SERVER = re.compile(r"(med|bio)rxiv\.org/content/", re.I)


def _publisher_native(*, url: str, doi: str | None) -> tuple[Candidate, ...]:
    """Full text from the publisher itself, for publishers that serve it.

    Europe PMC is tried first for any DOI, but deposit lags publication by
    weeks: every PLOS paper in this corpus answers `pmcid=None, isOpenAccess=N`
    while being freely available as XML from PLOS the day it appears. A feed of
    new science reads exactly the articles PMC has not indexed yet, so the
    publisher's own copy is the one that matters.

    JATS is listed before PDF so a marked-up copy always wins where one exists.
    """

    candidates: list[Candidate] = []

    if doi and (match := _PLOS_DOI.match(doi.strip())):
        journal = _PLOS_JOURNALS.get(match.group(1).casefold())
        if journal:
            candidates.append(
                Candidate(
                    url=(
                        f"https://journals.plos.org/{journal}/article/file"
                        f"?id={quote(doi.strip())}&type=manuscript"
                    ),
                    source="plos_jats",
                    parser="jats",
                    expected_kind=TextKind.FULL_TEXT,
                    licence="cc-by",
                )
            )

    # eLife articles carry their id in the URL, which is the only identifier we
    # hold for them: none of the eLife items in this corpus has a stored DOI.
    if url and (match := _ELIFE_ARTICLE.search(url)):
        candidates.append(
            Candidate(
                url=f"https://elifesciences.org/articles/{match.group(1)}.xml",
                source="elife_jats",
                parser="jats",
                expected_kind=TextKind.FULL_TEXT,
                licence="cc-by",
            )
        )

    # medRxiv and bioRxiv landing pages carry the abstract and nothing else, and
    # their DOI prefix is too recent for OpenAlex or PMC to offer a route, so
    # every one of these items sat at four to six hundred words. Appending
    # ".full" does not help — the server returns the same abstract page when it
    # has no HTML rendering — but the PDF is always there, and reading it turned
    # 451 stored words into 8,245 with methods and results intact.
    if url and (match := _PREPRINT_SERVER.search(url)):
        parts = urlsplit(url)
        path = parts.path.rstrip("/")
        if not path.endswith(".full.pdf"):
            path = f"{path.removesuffix('.full')}.full.pdf"
        candidates.append(
            Candidate(
                url=urlunsplit((parts.scheme, parts.netloc, path, "", "")),
                source=f"{match.group(1).casefold()}rxiv_pdf",
                parser="pdf",
                expected_kind=TextKind.FULL_TEXT,
            )
        )

    return tuple(candidates)


def discover_candidates(
    fetcher: Fetcher,
    *,
    url: str,
    arxiv_id: str | None = None,
    doi: str | None = None,
    is_paper: bool = False,
) -> tuple[Candidate, ...]:
    """Order the ways this item's text might be obtained, richest first.

    Structured sources lead because they state their own sections, figures, and
    tables. A PDF is last: its structure has to be reconstructed from geometry,
    and every earlier option avoids that.
    """

    candidates: list[Candidate] = []

    if arxiv_id:
        bare = arxiv_id.strip()
        candidates.append(
            Candidate(
                url=f"https://arxiv.org/html/{bare}",
                source="arxiv_html",
                parser="arxiv",
                expected_kind=TextKind.FULL_TEXT,
            )
        )
        candidates.append(
            Candidate(
                url=f"https://arxiv.org/pdf/{bare}",
                source="arxiv_pdf",
                parser="pdf",
                expected_kind=TextKind.FULL_TEXT,
            )
        )

    if doi:
        pmcid = _europe_pmc_id(fetcher, doi)
        if pmcid:
            candidates.insert(
                0,
                Candidate(
                    url=EUROPE_PMC_FULLTEXT.format(pmcid=pmcid),
                    source="pmc_jats",
                    parser="jats",
                    expected_kind=TextKind.FULL_TEXT,
                ),
            )
        candidates.extend(_openalex_locations(fetcher, doi))

    # The item's own page. For journalism it is the only candidate; for a paper
    # it is a last resort behind every open-access copy.
    if url:
        candidates.append(
            Candidate(
                url=url,
                source="article_html",
                parser="article",
                open_access=not is_paper,
            )
        )

    # Ahead of everything, including Europe PMC: same JATS, no deposit lag.
    for candidate in reversed(_publisher_native(url=url, doi=doi)):
        candidates.insert(0, candidate)

    seen: set[str] = set()
    ordered: list[Candidate] = []
    for candidate in candidates:
        if candidate.url in seen:
            continue
        seen.add(candidate.url)
        ordered.append(candidate)
    return tuple(ordered)


def _parse(candidate: Candidate, body: bytes, text: str) -> Document:
    if candidate.parser == "arxiv":
        # The candidate's URL is what LaTeXML's relative image srcs resolve
        # against. arXiv serves /html/{id} without redirecting, so the URL we
        # asked for is the one the paths are relative to.
        return extract_arxiv_html(text, base_url=candidate.url)
    if candidate.parser == "jats":
        return extract_jats(
            text,
            source=candidate.source,
            base_url=candidate.url,
        )
    if candidate.parser == "pdf":
        return extract_pdf(body)
    return extract_article(text)


def _kind_of(candidate: Candidate, document: Document) -> TextKind:
    """What this response actually contains, separate from access rights."""

    if candidate.expected_kind is not None:
        return candidate.expected_kind
    # HTML landing pages are ambiguous. The article extractor separates a
    # labelled abstract from body prose, so this is direct parsed evidence
    # rather than a length/heading quota. A report or dataset page with a real
    # body remains full text; a preprint landing page containing only its
    # abstract does not.
    if document.abstract and not document.body_text.strip():
        return TextKind.ABSTRACT
    return TextKind.FULL_TEXT


def _preview_image(fetches: list[RawFetch]) -> str | None:
    """Recover a declared article preview from bodies already fetched."""

    for fetch in fetches:
        if fetch.parser != "article" or not fetch.body:
            continue
        image = extract_html_preview_image(
            fetch.body.decode("utf-8", errors="replace"),
            base_url=fetch.final_url or fetch.url,
        )
        if image:
            return image
    return None


def resolve_item_text(
    fetcher: Fetcher,
    *,
    url: str,
    arxiv_id: str | None = None,
    doi: str | None = None,
    is_paper: bool = False,
) -> Resolution:
    """Fetch an item's text every way available and keep the best result.

    Candidates are tried richest-first and the walk stops as soon as one is
    clearly good enough, so a paper whose LaTeXML renders well never has its
    PDF pulled.
    """

    candidates = discover_candidates(
        fetcher, url=url, arxiv_id=arxiv_id, doi=doi, is_paper=is_paper
    )
    if not candidates:
        return Resolution(
            status=ResolutionStatus.NOT_FOUND,
            error="no candidate sources for this item",
        )

    scored: list[ScoredDocument] = []
    attempted: list[str] = []
    licences: dict[str, str | None] = {}
    scored_kinds: list[tuple[ScoredDocument, TextKind]] = []
    outcomes: list[str] = []
    fetches: list[RawFetch] = []

    for candidate in candidates:
        attempted.append(candidate.source)
        result = fetcher.fetch(candidate.url)
        if not result.ok or not result.body:
            outcomes.append(f"{candidate.source}: {result.outcome.value}")
            continue

        # Recorded before parsing, and kept even for candidates that go on to
        # lose or to extract nothing: a body that reads as empty today is
        # exactly what a fixed extractor needs to be re-run against.
        fetches.append(
            RawFetch(
                source=candidate.source,
                parser=candidate.parser,
                url=candidate.url,
                body=result.body,
                final_url=result.final_url,
                status_code=result.status_code,
                content_type=result.content_type,
            )
        )

        document = _parse(candidate, result.body, result.text())
        if document.word_count == 0:
            outcomes.append(f"{candidate.source}: no text extracted")
            continue

        assessment = assess_text(document.text, has_structure=document.has_structure)
        if assessment.verdict is TextVerdict.SOFT_PAYWALL:
            outcomes.append(f"{candidate.source}: soft paywall")
            continue
        if assessment.verdict is TextVerdict.TOO_SHORT:
            # A redirect stub or a stripped page. Storing it as ok would let a
            # status of "ok" mean text nothing can be grounded on.
            outcomes.append(
                f"{candidate.source}: too short ({assessment.words} words)"
            )
            continue

        entry = score_document(document, source=candidate.source)
        licences[candidate.source] = candidate.licence
        scored_kinds.append((entry, _kind_of(candidate, document)))
        scored.append(entry)
        outcomes.append(f"{candidate.source}: scored {entry.score:.2f}")
        if is_good_enough(entry):
            break

    best = pick_best(tuple(scored))
    if best is None:
        # Distinguish "they refused" from "there was nothing there", since only
        # the second is worth retrying later.
        status = ResolutionStatus.NOT_FOUND
        if any("paywall" in outcome for outcome in outcomes):
            status = ResolutionStatus.PAYWALLED
        elif any(
            FetchOutcome.BLOCKED_BY_ROBOTS.value in outcome for outcome in outcomes
        ):
            status = ResolutionStatus.BLOCKED
        return Resolution(
            status=status,
            fetches=tuple(fetches),
            attempted=tuple(attempted),
            reasons=tuple(outcomes),
            error="; ".join(outcomes[:3]) or "no candidate produced text",
            image_url=_preview_image(fetches),
        )

    # Structure and length help choose between copies, but neither decides
    # completeness. That comes from the route and the parsed abstract/body
    # distinction above. Tiny/stub text was already rejected by assess_text.
    kind = next(kind for entry, kind in scored_kinds if entry is best)

    # The winner's bibliography if it has one, otherwise the best-scoring
    # candidate that does. Every candidate is a copy of the same article, so a
    # reference list taken from one of them describes this item either way; the
    # source is recorded because the citation sentences then come from that
    # copy's prose rather than from the text stored above.
    references = best.document.references
    reference_source = best.source if references else None
    if not references:
        for entry in sorted(scored, key=lambda item: -item.score):
            if entry.document.references:
                references = entry.document.references
                reference_source = entry.source
                break

    return Resolution(
        status=ResolutionStatus.OK,
        source=best.source,
        kind=kind,
        document=best.document,
        score=best.score,
        licence=licences.get(best.source),
        references=references,
        reference_source=reference_source,
        fetches=tuple(fetches),
        attempted=tuple(attempted),
        reasons=(*outcomes, *best.reasons),
        image_url=_preview_image(fetches),
    )
