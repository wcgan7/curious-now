from __future__ import annotations

from calendar import timegm
from datetime import UTC, datetime
from enum import StrEnum
from html import unescape
from typing import Any
from uuid import UUID

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from pydantic import BaseModel, ConfigDict

from curious_now_v2.core.source_registry import FeedSpec, SourceSpec
from curious_now_v2.pipeline.ingest import (
    IngestCandidate,
    RawFeedEntry,
    normalize_entry,
)


class FeedReadStatus(StrEnum):
    SUCCEEDED = "succeeded"
    NOT_MODIFIED = "not_modified"


class FeedBatch(BaseModel):
    """One network fetch, including cache validators and normalized entries."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID
    feed_url: str
    status: FeedReadStatus
    http_status: int
    etag: str | None
    last_modified: str | None
    candidates: tuple[IngestCandidate, ...]
    skipped_entries: int


def _entry_value(entry: Any, key: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


def _plain_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    if "<" in value and ">" in value:
        text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    else:
        text = unescape(value)
    return " ".join(text.split()) or None


def _published_at(entry: Any) -> datetime | None:
    parsed = _entry_value(entry, "published_parsed") or _entry_value(
        entry,
        "updated_parsed",
    )
    if parsed is not None:
        try:
            return datetime.fromtimestamp(timegm(parsed), tz=UTC)
        except (OverflowError, TypeError, ValueError):
            pass

    raw = _entry_value(entry, "published") or _entry_value(entry, "updated")
    if isinstance(raw, str) and raw.strip():
        try:
            value = date_parser.parse(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    return None


def fetch_feed(
    *,
    client: httpx.Client,
    source_id: UUID,
    source: SourceSpec,
    feed: FeedSpec,
    etag: str | None = None,
    last_modified: str | None = None,
) -> FeedBatch:
    """Fetch and normalize a configured feed without writing to the database."""

    headers = {
        "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml",
        "User-Agent": "CuriousNow/2 (+https://github.com/curious-now)",
    }
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    response = client.get(feed.url, headers=headers, follow_redirects=True)
    if response.status_code == httpx.codes.NOT_MODIFIED:
        return FeedBatch(
            source_id=source_id,
            feed_url=feed.url,
            status=FeedReadStatus.NOT_MODIFIED,
            http_status=response.status_code,
            etag=etag,
            last_modified=last_modified,
            candidates=(),
            skipped_entries=0,
        )
    response.raise_for_status()

    parsed = feedparser.parse(response.content)
    entries = parsed.get("entries", ())
    if parsed.get("bozo") and not entries:
        error = parsed.get("bozo_exception")
        raise ValueError(f"feed could not be parsed: {error}")

    candidates: list[IngestCandidate] = []
    skipped_entries = 0
    for entry in entries:
        title = _plain_text(_entry_value(entry, "title"))
        url = _entry_value(entry, "link")
        if not title or not isinstance(url, str) or not url.strip():
            skipped_entries += 1
            continue

        summary = _plain_text(
            _entry_value(entry, "summary")
            or _entry_value(entry, "description")
        )
        native_id = _entry_value(entry, "id") or _entry_value(entry, "guid")
        try:
            raw_entry = RawFeedEntry(
                source_id=source_id,
                source_name=source.name,
                source_role=source.role,
                source_native_id=str(native_id) if native_id else None,
                title=title,
                url=url,
                summary=summary,
                published_at=_published_at(entry),
                default_content_type=feed.default_content_type,
            )
            candidates.append(normalize_entry(raw_entry))
        except ValueError:
            skipped_entries += 1

    return FeedBatch(
        source_id=source_id,
        feed_url=feed.url,
        status=FeedReadStatus.SUCCEEDED,
        http_status=response.status_code,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
        candidates=tuple(candidates),
        skipped_entries=skipped_entries,
    )
