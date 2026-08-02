"""Recovering identifiers for references that were cited without one.

A third of this corpus's references carry no DOI or arXiv id in their markup,
and 62% within arXiv, because conference papers are routinely cited without
one. Those references cannot become nodes: a citation string alone cannot be
deduplicated, so keying a paper on it would mint a fresh node per spelling.

Crossref's query.bibliographic takes a reference exactly as printed and returns
the work it denotes. That matters more than it sounds: the first attempt here
guessed a title out of the citation string and searched on that, which worked on
one arXiv paper and failed on nearly every other bibliography style --
"Pinazo, A.; Manresa, M. A." yielded "A.; Marques, A", and styles that print the
year before the title yielded no title at all. Handing over the whole string
removes the guess rather than repairing it. Measured on the citations that
defeated the guess: 9 of 14 matched, none failed.

The remaining difficulty is telling a good match from a confident wrong one. A
bibliographic match is a judgement, unlike an identifier read from markup, and a
wrong one is worse than none: it invents a paper and hangs an edge off it, and
nothing downstream can tell that from a real one. So a returned title is checked
back against the citation string it came from, together with the authors, and
anything short of strong agreement is declined. Of the five declined above,
every one was a genuinely different paper.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

CROSSREF_WORKS = "https://api.crossref.org/works"
USER_AGENT = "curious-now/0.1 (reference resolution)"

# Crossref advertises its own limit in every reply -- X-Rate-Limit-Limit: 1 over
# X-Rate-Limit-Interval: 1s for anonymous callers. Pacing at 0.6s earned a run
# of 429s within six requests, so this sits just above what they ask for rather
# than just below it. Eight thousand lookups take about two and a half hours.
REQUEST_INTERVAL_SECONDS = 1.1
TIMEOUT_SECONDS = 30.0
# A burst of refusals is worth waiting out; a sustained one means stop.
MAX_RATE_LIMIT_RETRIES = 3
BACKOFF_SECONDS = 5.0

# Agreement required between the matched title and the citation string.
MIN_TITLE_OVERLAP = 0.85
# Without a confirming author, the title has to agree almost completely.
STRICT_TITLE_OVERLAP = 0.95
# Below this there is not enough of a citation to match on.
MIN_CITATION_CHARS = 40
MAX_QUERY_CHARS = 400

# LaTeXML appends its own back-references to every arXiv bibliography entry --
# "Cited by: §A.1, Appendix B, Lemma C.23" -- which are ours, not the citation's.
_CITED_BY = re.compile(r"\s*Cited by:.*$", re.I | re.S)
# Trailing link furniture from the same source.
_EXTERNAL_LINKS = re.compile(r"\s*External Links:.*$", re.I | re.S)

_WORD = re.compile(r"[a-z0-9]+")
# Words that agree by accident; they inflate overlap without evidencing a match.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of",
        "on", "or", "the", "to", "via", "with", "using", "based",
    }
)


class LookupUnavailable(RuntimeError):
    """The index could not be asked — a refusal, not an absence of matches.

    Distinguished because the two look identical to a caller and mean opposite
    things. Reporting a rate limit as "no match found" turned a blocked run into
    an apparent 20% match rate, and the number was believed until the raw
    response was read.
    """


def clean_citation(citation_text: str) -> str:
    """The citation as printed, without the reader's own annotations."""

    without = _CITED_BY.sub("", citation_text)
    without = _EXTERNAL_LINKS.sub("", without)
    return " ".join(without.split())


def _tokens(value: str) -> list[str]:
    return [
        word
        for word in _WORD.findall(value.casefold())
        if word not in _STOPWORDS and len(word) > 1
    ]


def title_overlap(candidate_title: str, citation_text: str) -> float:
    """How much of a matched title actually appears in the citation string.

    Measured against the citation rather than anything we derived from it: the
    citation is the one part of this that cannot be wrong.
    """

    wanted = _tokens(candidate_title)
    if not wanted:
        return 0.0
    present = set(_tokens(citation_text))
    return sum(1 for word in wanted if word in present) / len(wanted)


@dataclass(frozen=True)
class Match:
    doi: str | None
    arxiv_id: str | None
    title: str
    confidence: float

    @property
    def has_identifier(self) -> bool:
        return bool(self.doi or self.arxiv_id)


def _title_of(item: dict[str, Any]) -> str:
    titles = item.get("title") or []
    return " ".join(str(titles[0]).split()) if titles else ""

def _arxiv_of(item: dict[str, Any]) -> str | None:
    doi = (item.get("DOI") or "").casefold()
    if "10.48550/arxiv." in doi:
        return doi.split("10.48550/arxiv.", 1)[1]
    return None


_CITATION_YEAR = re.compile(r"\b(19[5-9]\d|20[0-5]\d)\b")
# A preprint and its published version are the same work a year or two apart, so
# a small gap is normal. A larger one means a different paper with a similar
# title -- a 2016 citation matched to a 2019 article, seen in the first batch.
MAX_YEAR_GAP = 2


def _issued_year(item: dict[str, Any]) -> int | None:
    parts = ((item.get("issued") or {}).get("date-parts") or [[]])[0]
    if parts and isinstance(parts[0], int):
        return parts[0]
    return None


def year_disagrees(item: dict[str, Any], citation_text: str) -> bool:
    """Whether the matched work's year is absent from the citation's years.

    Only decisive when both sides name one. Plenty of citations omit the year
    entirely, and silence is not disagreement.
    """

    issued = _issued_year(item)
    if issued is None:
        return False
    years = {int(found) for found in _CITATION_YEAR.findall(citation_text)}
    if not years:
        return False
    return min(abs(issued - year) for year in years) > MAX_YEAR_GAP


def _authors_agree(item: dict[str, Any], citation_text: str) -> bool:
    """Whether a listed author's surname appears in the citation.

    Only the first few are checked: a citation abbreviates a long author list to
    "et al.", so the absence of the tenth author says nothing.
    """

    flat = citation_text.casefold()
    surnames = [
        str(author.get("family") or "")
        for author in (item.get("author") or [])
        if author.get("family")
    ]
    return any(name.casefold() in flat for name in surnames[:4])


def _retry_after(error: urllib.error.HTTPError, attempt: int) -> float:
    headers: Any = error.headers
    raw = headers.get("retry-after") if headers is not None else None
    if raw:
        try:
            return min(float(raw), 60.0)
        except (TypeError, ValueError):
            pass
    return BACKOFF_SECONDS * (attempt + 1)


def search(
    citation_text: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any] | None:
    """The work Crossref believes this citation denotes, or None if none.

    A rate-limit refusal is waited out and retried, because one 429 in a run of
    eight thousand is a moment's impatience rather than a reason to stop. A
    refusal that survives the retries raises LookupUnavailable, which the caller
    must not count among its misses: "the index would not answer" and "the index
    has no such paper" mean opposite things.
    """

    query = urllib.parse.quote(citation_text[:MAX_QUERY_CHARS])
    url = (
        f"{CROSSREF_WORKS}?rows=1&select=DOI,title,author,score,issued"
        f"&query.bibliographic={query}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(MAX_RATE_LIMIT_RETRIES):
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in {429, 503} and attempt + 1 < MAX_RATE_LIMIT_RETRIES:
                sleeper(_retry_after(error, attempt))
                continue
            detail = ""
            try:
                detail = error.read()[:200].decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                detail = ""
            raise LookupUnavailable(f"HTTP {error.code}: {detail}") from error
        except (OSError, TimeoutError) as error:
            # OSError covers URLError and every socket-level failure beneath it.
            raise LookupUnavailable(str(error)) from error
        except ValueError as error:
            raise LookupUnavailable(f"unreadable reply: {error}") from error

        items = (payload.get("message") or {}).get("items") or []
        return items[0] if items else None

    raise LookupUnavailable("rate limited after retries")


def resolve(
    citation_text: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> Match | None:
    """Find the work a citation string denotes, or decline to guess.

    Returns None rather than a weak match. A reference left unidentified stays a
    reference; a reference wrongly identified becomes a node in the graph that
    no later pass would think to question.
    """

    citation = clean_citation(citation_text)
    if len(citation) < MIN_CITATION_CHARS:
        return None

    item = search(citation, opener=opener, sleeper=sleeper)
    if item is None:
        return None

    title = _title_of(item)
    if not title:
        return None

    overlap = title_overlap(title, citation)
    agrees = _authors_agree(item, citation)
    if overlap < MIN_TITLE_OVERLAP:
        return None
    if not agrees and overlap < STRICT_TITLE_OVERLAP:
        return None
    if year_disagrees(item, citation):
        # Same title, different paper. Titles repeat across years far more often
        # than a matcher scoring only on words would suggest.
        return None

    doi = (item.get("DOI") or "").strip() or None
    match = Match(
        doi=doi,
        arxiv_id=_arxiv_of(item),
        title=title,
        # The author agreeing is real evidence, but the title carries the claim.
        confidence=round(min(1.0, overlap + (0.03 if agrees else 0.0)), 3),
    )
    return match if match.has_identifier else None


def pace(last_request_at: float) -> float:
    """Sleep as needed to hold the request interval, returning the new mark."""

    elapsed = time.monotonic() - last_request_at
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
    return time.monotonic()
