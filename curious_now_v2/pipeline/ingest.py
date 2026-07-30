from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from curious_now_v2.core.enums import AccessClass, ContentType, SourceRole
from curious_now_v2.core.source_registry import ContentTypeRule

_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = frozenset(
    {
        "cmpid",
        "fbclid",
        "gclid",
        "icid",
        "mc_cid",
        "mc_eid",
        "ocid",
        "ref",
        "ref_src",
    }
)
_ARXIV_NEW_RE = re.compile(r"\b\d{4}\.\d{4,5}(?:v\d+)?\b", re.IGNORECASE)
_ARXIV_OLD_RE = re.compile(r"\b[a-z-]+/\d{7}(?:v\d+)?\b", re.IGNORECASE)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class RawFeedEntry(BaseModel):
    """Provider-neutral data retained from an RSS, Atom, or API response."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID
    source_name: str = Field(min_length=1)
    source_role: SourceRole
    source_native_id: str | None = None
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    summary: str | None = None
    published_at: datetime | None = None
    default_content_type: ContentType
    content_type_rules: tuple[ContentTypeRule, ...] = ()


class IngestCandidate(BaseModel):
    """Deterministic database input produced before clustering or AI work."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID
    source_name: str
    source_role: SourceRole
    source_native_id: str | None
    title: str
    url: str
    canonical_url: str
    canonical_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    snippet: str | None
    content_type: ContentType
    # Where the type came from, which decides what may be claimed from it.
    # See classify_content_type: a default from a single-kind feed describes
    # the item; a default reached on a mixed feed describes nothing.
    content_type_basis: str = "feed_default"
    content_type_note: str | None = None
    access_class: AccessClass
    published_at: datetime | None
    doi: str | None
    arxiv_id: str | None


def classify_content_type(
    entry: RawFeedEntry, canonical_url: str, doi: str | None
) -> tuple[ContentType, str, str | None]:
    """Type one item from itself where possible, from its feed otherwise.

    Returns the type with the basis for it, because those are different facts
    and only one of them can be shown to a reader.

    A default is not worthless — arXiv's feed carries preprints and nothing
    else, so "preprint" describes every item on it. It fails on a feed that
    carries several kinds, which is how a Nature book review came to be labelled
    peer reviewed, ranked above real research, and announced to the model as a
    peer-reviewed paper. Rules are only written for a feed found to be mixed, so
    their presence is what separates the two cases.
    """

    for rule in entry.content_type_rules:
        if rule.matches(canonical_url, entry.url, doi):
            return rule.content_type, "source_pattern", rule.note or (
                f"matched {rule.pattern!r}"
            )
    if entry.content_type_rules:
        # Rules exist because this feed was found to carry more than one kind of
        # thing, so its default is a fallback rather than a description, and an
        # item none of them recognises is genuinely unclassified.
        return entry.default_content_type, "feed_unmatched", (
            "no rule matched; the feed default is a fallback here"
        )
    return entry.default_content_type, "feed_default", None


def canonicalize_url(url: str) -> str:
    """Return an absolute, tracker-free URL suitable for exact deduplication."""

    raw = url.strip()
    if "://" not in raw:
        raw = f"https://{raw}"

    parts = urlsplit(raw)
    scheme = parts.scheme.casefold()
    if scheme not in {"http", "https"}:
        raise ValueError("only HTTP(S) item URLs are supported")
    if not parts.hostname:
        raise ValueError("item URL must include a hostname")

    hostname = parts.hostname.casefold()
    port = parts.port
    if port is not None and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")

    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        normalized_key = key.strip().casefold()
        if normalized_key.startswith(_TRACKING_PARAM_PREFIXES):
            continue
        if normalized_key in _TRACKING_PARAMS:
            continue
        query_items.append((key.strip(), value))
    query_items.sort(key=lambda item: (item[0], item[1]))

    return urlunsplit(
        (
            scheme,
            netloc,
            path,
            urlencode(query_items, doseq=True),
            "",
        )
    )


def extract_scholarly_ids(text: str) -> tuple[str | None, str | None]:
    """Extract normalized arXiv and DOI identifiers from provider text."""

    arxiv_match = _ARXIV_NEW_RE.search(text) or _ARXIV_OLD_RE.search(text)
    arxiv_id = arxiv_match.group(0).casefold() if arxiv_match else None

    doi_match = _DOI_RE.search(text)
    doi = None
    if doi_match:
        candidate = _CAMEL_SPLIT_RE.split(doi_match.group(0))[0]
        doi = candidate.rstrip("-_./").casefold() or None
    return arxiv_id, doi


def normalize_entry(entry: RawFeedEntry) -> IngestCandidate:
    """Normalize one raw entry without network, database, or model calls."""

    canonical_url = canonicalize_url(entry.url)
    identifier_text = " ".join(
        value for value in (entry.url, entry.title, entry.summary) if value
    )
    arxiv_id, doi = extract_scholarly_ids(identifier_text)
    snippet = entry.summary.strip() if entry.summary and entry.summary.strip() else None
    content_type, basis, note = classify_content_type(entry, canonical_url, doi)

    return IngestCandidate(
        source_id=entry.source_id,
        source_name=entry.source_name,
        source_role=entry.source_role,
        source_native_id=entry.source_native_id,
        title=" ".join(entry.title.split()),
        url=entry.url.strip(),
        canonical_url=canonical_url,
        canonical_hash=hashlib.sha256(canonical_url.encode()).hexdigest(),
        snippet=snippet,
        content_type=content_type,
        content_type_basis=basis,
        content_type_note=note,
        access_class=AccessClass.SNIPPET if snippet else AccessClass.METADATA_ONLY,
        published_at=entry.published_at,
        doi=doi,
        arxiv_id=arxiv_id,
    )
