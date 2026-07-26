from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from curious_now_v2.core.enums import AccessClass, ExplanationDepth
from curious_now_v2.core.models import EvidencePacket, StoryDraft


class ExplanationPlan(BaseModel):
    """The explanation work justified by the available evidence."""

    model_config = ConfigDict(frozen=True)

    story_id: UUID
    evidence_packet_id: UUID | None
    depths: tuple[ExplanationDepth, ...]
    skipped_reasons: dict[ExplanationDepth, str]


def plan_explanations(
    story: StoryDraft,
    packet: EvidencePacket | None,
) -> ExplanationPlan:
    """Choose explanation depths without making them publication requirements."""

    if packet is None or not packet.claims:
        reason = "no supported evidence claims"
        return ExplanationPlan(
            story_id=story.story_id,
            evidence_packet_id=packet.packet_id if packet else None,
            depths=(),
            skipped_reasons={
                ExplanationDepth.GLANCE: reason,
                ExplanationDepth.EXPLAIN: reason,
                ExplanationDepth.TECHNICAL: reason,
            },
        )

    depths: list[ExplanationDepth] = [ExplanationDepth.GLANCE]
    skipped: dict[ExplanationDepth, str] = {}

    if packet.text_sufficiency in {
        AccessClass.SNIPPET,
        AccessClass.ABSTRACT,
        AccessClass.OPEN_FULL_TEXT,
    }:
        depths.append(ExplanationDepth.EXPLAIN)
    else:
        skipped[ExplanationDepth.EXPLAIN] = "metadata-only evidence is insufficient"

    if story.has_primary_research and packet.text_sufficiency is AccessClass.OPEN_FULL_TEXT:
        depths.append(ExplanationDepth.TECHNICAL)
    elif not story.has_primary_research:
        skipped[ExplanationDepth.TECHNICAL] = "story has no primary research"
    else:
        skipped[ExplanationDepth.TECHNICAL] = "open primary text is unavailable"

    return ExplanationPlan(
        story_id=story.story_id,
        evidence_packet_id=packet.packet_id,
        depths=tuple(depths),
        skipped_reasons=skipped,
    )
