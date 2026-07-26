from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from curious_now_v2.core.enums import (
    AccessClass,
    ClaimKind,
    ContentType,
    ExplanationDepth,
    ExplanationStatus,
    SourceRole,
    StoryItemRole,
)


class SourceItem(BaseModel):
    """A visible source item attached to a story."""

    model_config = ConfigDict(frozen=True)

    item_id: UUID
    source_id: UUID
    source_name: str = Field(min_length=1)
    source_role: SourceRole
    role: StoryItemRole
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    content_type: ContentType
    access_class: AccessClass = AccessClass.METADATA_ONLY
    published_at: datetime | None = None
    paper_id: UUID | None = None

    @property
    def is_primary_research(self) -> bool:
        return self.content_type in {
            ContentType.PREPRINT,
            ContentType.PEER_REVIEWED,
        } or self.source_role is SourceRole.PRIMARY_RESEARCH


class EvidenceSupport(BaseModel):
    """Provenance connecting a claim to a visible source item."""

    model_config = ConfigDict(frozen=True)

    item_id: UUID
    excerpt: str | None = None
    locator: dict[str, str | int] = Field(default_factory=dict)


class EvidenceClaim(BaseModel):
    """A factual unit that explanations are allowed to express."""

    model_config = ConfigDict(frozen=True)

    claim_id: UUID = Field(default_factory=uuid4)
    kind: ClaimKind
    text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    supports: tuple[EvidenceSupport, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def support_items_must_be_unique(self) -> EvidenceClaim:
        item_ids = [support.item_id for support in self.supports]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("a claim cannot cite the same item more than once")
        return self


class EvidencePacket(BaseModel):
    """The versioned factual interface between retrieval and generation."""

    model_config = ConfigDict(frozen=True)

    packet_id: UUID = Field(default_factory=uuid4)
    story_id: UUID
    version: int = Field(ge=1)
    text_sufficiency: AccessClass
    central_claim: str | None = None
    claims: tuple[EvidenceClaim, ...] = ()
    why_it_matters: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    created_at: datetime

    @model_validator(mode="after")
    def claim_ids_must_be_unique(self) -> EvidencePacket:
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("evidence packet claim IDs must be unique")
        return self

    @property
    def cited_item_ids(self) -> frozenset[UUID]:
        return frozenset(
            support.item_id
            for claim in self.claims
            for support in claim.supports
        )


class StoryDraft(BaseModel):
    """The pipeline representation of a candidate or published story."""

    model_config = ConfigDict(frozen=True)

    story_id: UUID
    canonical_title: str = Field(min_length=1)
    items: tuple[SourceItem, ...] = Field(min_length=1)
    current_evidence_packet_id: UUID | None = None

    @model_validator(mode="after")
    def item_ids_must_be_unique(self) -> StoryDraft:
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("a story cannot contain the same item more than once")
        return self

    @property
    def item_ids(self) -> frozenset[UUID]:
        return frozenset(item.item_id for item in self.items)

    @property
    def has_primary_research(self) -> bool:
        return any(item.is_primary_research for item in self.items)

    @property
    def best_access_class(self) -> AccessClass:
        order = {
            AccessClass.METADATA_ONLY: 0,
            AccessClass.SNIPPET: 1,
            AccessClass.ABSTRACT: 2,
            AccessClass.OPEN_FULL_TEXT: 3,
        }
        return max(
            (item.access_class for item in self.items),
            key=order.__getitem__,
        )


class Explanation(BaseModel):
    """A generated view derived from exactly one evidence-packet version."""

    model_config = ConfigDict(frozen=True, protected_namespaces=())

    explanation_id: UUID = Field(default_factory=uuid4)
    story_id: UUID
    evidence_packet_id: UUID
    depth: ExplanationDepth
    status: ExplanationStatus
    plain_text: str | None = None
    content: dict[str, object] = Field(default_factory=dict)
    prompt_version: str = Field(min_length=1)
    model_provider: str | None = None
    model_name: str | None = None
    failure_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def valid_explanations_need_content(self) -> Explanation:
        if (
            self.status is ExplanationStatus.VALID
            and not (self.plain_text and self.plain_text.strip())
            and not self.content
        ):
            raise ValueError("a valid explanation must contain text or structured content")
        if self.status is ExplanationStatus.FAILED and not self.failure_reason:
            raise ValueError("a failed explanation must include a failure reason")
        return self
