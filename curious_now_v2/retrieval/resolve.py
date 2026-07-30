from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum

from curious_now_v2.retrieval.document import Document
from curious_now_v2.retrieval.extract_article import extract_article
from curious_now_v2.retrieval.extract_arxiv import extract_arxiv_html
from curious_now_v2.retrieval.extract_jats import extract_jats
from curious_now_v2.retrieval.extract_pdf import extract_pdf
from curious_now_v2.retrieval.fetch import Fetcher, FetchOutcome
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
    open_access: bool = True
    licence: str | None = None


@dataclass(frozen=True)
class Resolution:
    status: ResolutionStatus
    source: str | None = None
    kind: TextKind | None = None
    document: Document | None = None
    score: float = 0.0
    licence: str | None = None
    attempted: tuple[str, ...] = field(default_factory=tuple)
    reasons: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None

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
                    licence=licence,
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
            )
        )
        candidates.append(
            Candidate(
                url=f"https://arxiv.org/pdf/{bare}",
                source="arxiv_pdf",
                parser="pdf",
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
        return extract_arxiv_html(text)
    if candidate.parser == "jats":
        return extract_jats(text)
    if candidate.parser == "pdf":
        return extract_pdf(body)
    return extract_article(text)


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
    outcomes: list[str] = []

    for candidate in candidates:
        attempted.append(candidate.source)
        result = fetcher.fetch(candidate.url)
        if not result.ok or not result.body:
            outcomes.append(f"{candidate.source}: {result.outcome.value}")
            continue

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
            attempted=tuple(attempted),
            reasons=tuple(outcomes),
            error="; ".join(outcomes[:3]) or "no candidate produced text",
        )

    assessment = assess_text(
        best.document.text, has_structure=best.document.has_structure
    )
    kind = (
        TextKind.FULL_TEXT
        if best.document.sections and assessment.words >= 600
        else TextKind.ABSTRACT
    )
    return Resolution(
        status=ResolutionStatus.OK,
        source=best.source,
        kind=kind,
        document=best.document,
        score=best.score,
        licence=licences.get(best.source),
        attempted=tuple(attempted),
        reasons=(*outcomes, *best.reasons),
    )
