from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from curious_now_v2.core.enums import ContentType, FeedKind, SourceRole


class SourcePolicy(BaseModel):
    """Evidence and extraction policy for one source."""

    model_config = ConfigDict(frozen=True)

    counts_as_independent: bool
    allow_full_text_extraction: bool = False
    notes: str | None = None


class FeedSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str = Field(min_length=1)
    kind: FeedKind = FeedKind.RSS
    default_content_type: ContentType
    fetch_interval_minutes: int = Field(default=60, gt=0)

    @field_validator("url")
    @classmethod
    def url_must_be_absolute_http(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("feed URL must be absolute HTTP(S)")
        return value


class SourceSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    homepage_url: str | None = None
    role: SourceRole
    feeds: tuple[FeedSpec, ...] = Field(min_length=1)
    policy: SourcePolicy
    active: bool = True

    @model_validator(mode="after")
    def feed_urls_must_be_unique(self) -> SourceSpec:
        urls = [feed.url for feed in self.feeds]
        if len(urls) != len(set(urls)):
            raise ValueError("a source cannot contain duplicate feed URLs")
        if (
            self.role is SourceRole.DISCOVERY
            and self.policy.counts_as_independent
        ):
            raise ValueError("discovery sources cannot count as independent evidence")
        return self


class SourceRegistry(BaseModel):
    """Versioned input to ingestion, separate from mutable fetch state."""

    model_config = ConfigDict(frozen=True)

    version: int = Field(ge=1)
    sources: tuple[SourceSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def sources_and_feeds_must_be_unique(self) -> SourceRegistry:
        names = [source.name.casefold() for source in self.sources]
        if len(names) != len(set(names)):
            raise ValueError("source names must be unique")

        feed_urls = [feed.url for source in self.sources for feed in source.feeds]
        if len(feed_urls) != len(set(feed_urls)):
            raise ValueError("feed URLs must be unique across the registry")
        return self


def load_source_registry(path: Path) -> SourceRegistry:
    """Read and validate a source registry before any database mutation."""

    return SourceRegistry.model_validate_json(path.read_text())
