from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from curious_now_v2.core.enums import (
    AccessClass,
    ClaimKind,
    ContentType,
    ExplanationDepth,
    SourceRole,
    StoryItemRole,
)


class SourceLinkView(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_id: UUID
    source_name: str
    source_role: SourceRole
    story_role: StoryItemRole
    title: str
    url: str
    content_type: ContentType
    access_class: AccessClass
    published_at: datetime | None


class CitationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_id: UUID
    source_name: str
    url: str
    excerpt: str | None
    locator: dict[str, str | int]


class ClaimView(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim_id: UUID
    kind: ClaimKind
    text: str
    confidence: float
    citations: tuple[CitationView, ...]


class ExplanationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    depth: ExplanationDepth
    plain_text: str | None
    content: dict[str, object]


class StoryReadModel(BaseModel):
    """Narrow contract consumed by the server-rendered reader."""

    model_config = ConfigDict(frozen=True)

    story_id: UUID
    title: str
    mode: Literal["evidence_only", "enriched"]
    sources: tuple[SourceLinkView, ...]
    claims: tuple[ClaimView, ...]
    available_depths: tuple[ExplanationDepth, ...]
    explanations: tuple[ExplanationView, ...]
