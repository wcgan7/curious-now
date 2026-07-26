from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from curious_now_v2.core.enums import ExplanationDepth, ExplanationStatus
from curious_now_v2.core.models import EvidencePacket, Explanation, StoryDraft
from curious_now_v2.pipeline.explanation_plan import plan_explanations


class PublicationMode(StrEnum):
    BLOCKED = "blocked"
    EVIDENCE_ONLY = "evidence_only"
    ENRICHED = "enriched"


class PublicationDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    publish: bool
    mode: PublicationMode
    reasons: tuple[str, ...]
    visible_item_ids: tuple[UUID, ...]
    available_depths: tuple[ExplanationDepth, ...]


def evaluate_publication(
    story: StoryDraft,
    *,
    packet: EvidencePacket | None = None,
    explanations: tuple[Explanation, ...] = (),
) -> PublicationDecision:
    """Return the reader mode without making AI a publication gate."""

    visible_item_ids = tuple(item.item_id for item in story.items if item.url.strip())
    if not story.canonical_title.strip():
        return PublicationDecision(
            publish=False,
            mode=PublicationMode.BLOCKED,
            reasons=("story title is empty",),
            visible_item_ids=visible_item_ids,
            available_depths=(),
        )
    if not visible_item_ids:
        return PublicationDecision(
            publish=False,
            mode=PublicationMode.BLOCKED,
            reasons=("story has no visible source links",),
            visible_item_ids=(),
            available_depths=(),
        )

    if packet is not None:
        if packet.story_id != story.story_id:
            return PublicationDecision(
                publish=False,
                mode=PublicationMode.BLOCKED,
                reasons=("evidence packet belongs to another story",),
                visible_item_ids=visible_item_ids,
                available_depths=(),
            )
        if story.current_evidence_packet_id != packet.packet_id:
            return PublicationDecision(
                publish=False,
                mode=PublicationMode.BLOCKED,
                reasons=("provided evidence packet is not the story's current packet",),
                visible_item_ids=visible_item_ids,
                available_depths=(),
            )
        unknown_support = packet.cited_item_ids - story.item_ids
        if unknown_support:
            return PublicationDecision(
                publish=False,
                mode=PublicationMode.BLOCKED,
                reasons=("evidence packet cites items outside the story",),
                visible_item_ids=visible_item_ids,
                available_depths=(),
            )

    explanation_plan = plan_explanations(story, packet)
    allowed_depths = frozenset(explanation_plan.depths)
    current_packet_id = story.current_evidence_packet_id
    valid_depths = sorted(
        {
            explanation.depth
            for explanation in explanations
            if explanation.status is ExplanationStatus.VALID
            and explanation.story_id == story.story_id
            and explanation.evidence_packet_id == current_packet_id
            and explanation.depth in allowed_depths
        },
        key=lambda depth: (
            ExplanationDepth.GLANCE,
            ExplanationDepth.EXPLAIN,
            ExplanationDepth.TECHNICAL,
        ).index(depth),
    )

    if not valid_depths:
        return PublicationDecision(
            publish=True,
            mode=PublicationMode.EVIDENCE_ONLY,
            reasons=("no current valid explanations; publish sources",),
            visible_item_ids=visible_item_ids,
            available_depths=(),
        )

    return PublicationDecision(
        publish=True,
        mode=PublicationMode.ENRICHED,
        reasons=("current evidence-backed explanations are available",),
        visible_item_ids=visible_item_ids,
        available_depths=tuple(valid_depths),
    )
