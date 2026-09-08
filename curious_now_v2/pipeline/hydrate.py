from __future__ import annotations

import re
from html import unescape
from typing import Any
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict, Field

from curious_now_v2.core.enums import AccessClass

ARXIV_API = "https://export.arxiv.org/api/query"
CROSSREF_API = "https://api.crossref.org/works"

# arXiv asks clients to batch rather than issue one request per identifier.
ARXIV_BATCH_SIZE = 50

ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

_JATS_TAG = re.compile(r"</?jats:[^>]+>")
_XML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
# JATS wraps the section heading in the abstract body, so stripping tags
# leaves a leading "Abstract" label that is not part of the text.
_LEADING_LABEL = re.compile(r"^(abstract|summary|graphical abstract)\b[:.\s-]*", re.I)

# Crossref returns some abstracts as a bare label with no content.
_USELESS_ABSTRACTS = frozenset({"abstract", "summary", "no abstract available"})

MIN_ABSTRACT_CHARS = 80

# 16 digits in groups of four; the last may be an X checksum.
_ORCID = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")


class PaperHydration(BaseModel):
    """An abstract recovered for one paper, with its provenance."""

    model_config = ConfigDict(frozen=True)

    abstract: str = Field(min_length=1)
    access_class: AccessClass
    extraction_method: str = Field(min_length=1)


class Author(BaseModel):
    """One author, exactly as the provider named them.

    Nothing here is normalized across providers. arXiv publishes a single
    display string and Crossref a given/family split, and reconciling those
    into one canonical person is the disambiguation problem the concept
    experiment lost to. `orcid` is the only field that identifies rather than
    describes, and only when the provider supplied it.
    """

    model_config = ConfigDict(frozen=True)

    position: int = Field(ge=0)
    full_name: str = Field(min_length=1)
    family: str | None = None
    given: str | None = None
    orcid: str | None = None
    affiliation: str | None = None


def clean_abstract(raw: str | None) -> str | None:
    """Normalize provider markup into plain text, or None if unusable."""

    if not raw:
        return None
    text = _JATS_TAG.sub(" ", raw)
    text = _XML_TAG.sub(" ", text)
    text = unescape(text)
    text = _WHITESPACE.sub(" ", text).strip()
    text = _LEADING_LABEL.sub("", text).strip()
    if not text:
        return None
    if text.casefold() in _USELESS_ABSTRACTS:
        return None
    if len(text) < MIN_ABSTRACT_CHARS:
        return None
    return text


def parse_arxiv_response(payload: bytes | str) -> dict[str, PaperHydration]:
    """Map arXiv Atom entries to hydrations keyed by bare arXiv ID."""

    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return {}

    results: dict[str, PaperHydration] = {}
    for entry in root.findall("atom:entry", ATOM_NS):
        identifier = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
        summary = entry.findtext("atom:summary", default="", namespaces=ATOM_NS)
        abstract = clean_abstract(summary)
        if not identifier or not abstract:
            continue
        results[_bare_arxiv_id(identifier)] = PaperHydration(
            abstract=abstract,
            access_class=AccessClass.ABSTRACT,
            extraction_method="arxiv_api",
        )
    return results


def _bare_arxiv_id(identifier: str) -> str:
    """The unversioned, case-folded identifier items are stored under."""

    arxiv_id = identifier.rsplit("/abs/", 1)[-1]
    # arXiv echoes the versioned ID; items store the bare identifier.
    bare_id = arxiv_id.split("v")[0] if re.search(r"v\d+$", arxiv_id) else arxiv_id
    return bare_id.casefold()


def parse_arxiv_authors(payload: bytes | str) -> dict[str, tuple[Author, ...]]:
    """Map arXiv Atom entries to author lists keyed by bare arXiv ID.

    Read from the same response the abstract came from, and deliberately not
    gated on that abstract: an entry whose summary is unusable still named its
    authors, and they are the part that does not go stale.
    """

    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return {}

    results: dict[str, tuple[Author, ...]] = {}
    for entry in root.findall("atom:entry", ATOM_NS):
        identifier = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
        if not identifier:
            continue
        authors: list[Author] = []
        for element in entry.findall("atom:author", ATOM_NS):
            name = _clean_name(element.findtext("atom:name", namespaces=ATOM_NS))
            if name is None:
                continue
            authors.append(
                Author(
                    position=len(authors),
                    full_name=name,
                    # arXiv publishes one display string. Splitting it into
                    # given and family would be our guess, not arXiv's, and a
                    # wrong guess on a name is worse than an absent one.
                    affiliation=_clean_name(
                        element.findtext("arxiv:affiliation", namespaces=ATOM_NS)
                    ),
                )
            )
        if authors:
            results[_bare_arxiv_id(identifier)] = tuple(authors)
    return results


def parse_crossref_work(payload: dict[str, Any]) -> PaperHydration | None:
    """Extract an abstract from one Crossref work response."""

    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    abstract = clean_abstract(message.get("abstract"))
    if not abstract:
        return None
    return PaperHydration(
        abstract=abstract,
        access_class=AccessClass.ABSTRACT,
        extraction_method="crossref_api",
    )


def parse_crossref_authors(payload: dict[str, Any]) -> tuple[Author, ...]:
    """Extract the author list from one Crossref work response.

    Crossref splits a name and sometimes carries an ORCID, which is the only
    identifier here worth joining on. `affiliation` is read where present and
    expected to be absent: it was an empty array for every author of the paper
    this parser was written against.
    """

    message = payload.get("message")
    if not isinstance(message, dict):
        return ()
    raw = message.get("author")
    if not isinstance(raw, list):
        return ()

    authors: list[Author] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        family = _clean_name(entry.get("family"))
        given = _clean_name(entry.get("given"))
        # A consortium or group author has a `name` and no family/given.
        full_name = " ".join(part for part in (given, family) if part) or _clean_name(
            entry.get("name")
        )
        if not full_name:
            continue
        authors.append(
            Author(
                position=len(authors),
                full_name=full_name,
                family=family,
                given=given,
                orcid=_clean_orcid(entry.get("ORCID")),
                affiliation=_first_affiliation(entry.get("affiliation")),
            )
        )
    return tuple(authors)


def _clean_name(value: object) -> str | None:
    """Collapse provider whitespace, or None where nothing is left."""

    if not isinstance(value, str):
        return None
    return _WHITESPACE.sub(" ", value).strip() or None


def _clean_orcid(value: object) -> str | None:
    """The bare ORCID, however the provider chose to wrap it in a URL.

    Crossref returns `https://orcid.org/0000-...` and has historically returned
    the `http://` form; storing the identifier rather than the URL is what
    makes two records of the same person compare equal.
    """

    text = _clean_name(value)
    if text is None:
        return None
    candidate = text.rsplit("/", 1)[-1].upper()
    return candidate if _ORCID.fullmatch(candidate) else None


def _first_affiliation(value: object) -> str | None:
    """The first named affiliation, which is all a single column can hold."""

    if not isinstance(value, list):
        return None
    for entry in value:
        if isinstance(entry, dict):
            name = _clean_name(entry.get("name"))
            if name:
                return name
    return None


def arxiv_batches(arxiv_ids: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Split identifiers into batches the arXiv API accepts in one query."""

    unique = tuple(dict.fromkeys(value for value in arxiv_ids if value.strip()))
    return tuple(
        unique[index : index + ARXIV_BATCH_SIZE]
        for index in range(0, len(unique), ARXIV_BATCH_SIZE)
    )
