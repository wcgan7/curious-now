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

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

_JATS_TAG = re.compile(r"</?jats:[^>]+>")
_XML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
# JATS wraps the section heading in the abstract body, so stripping tags
# leaves a leading "Abstract" label that is not part of the text.
_LEADING_LABEL = re.compile(r"^(abstract|summary|graphical abstract)\b[:.\s-]*", re.I)

# Crossref returns some abstracts as a bare label with no content.
_USELESS_ABSTRACTS = frozenset({"abstract", "summary", "no abstract available"})

MIN_ABSTRACT_CHARS = 80


class PaperHydration(BaseModel):
    """An abstract recovered for one paper, with its provenance."""

    model_config = ConfigDict(frozen=True)

    abstract: str = Field(min_length=1)
    access_class: AccessClass
    extraction_method: str = Field(min_length=1)


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
        arxiv_id = identifier.rsplit("/abs/", 1)[-1]
        # arXiv echoes the versioned ID; items store the bare identifier.
        bare_id = arxiv_id.split("v")[0] if re.search(r"v\d+$", arxiv_id) else arxiv_id
        results[bare_id.casefold()] = PaperHydration(
            abstract=abstract,
            access_class=AccessClass.ABSTRACT,
            extraction_method="arxiv_api",
        )
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


def arxiv_batches(arxiv_ids: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Split identifiers into batches the arXiv API accepts in one query."""

    unique = tuple(dict.fromkeys(value for value in arxiv_ids if value.strip()))
    return tuple(
        unique[index : index + ARXIV_BATCH_SIZE]
        for index in range(0, len(unique), ARXIV_BATCH_SIZE)
    )
