from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from curious_now_v2.core.enums import AccessClass, ClaimKind, ExplanationDepth
from curious_now_v2.core.models import EvidencePacket, StoryDraft

# Each layer's required content, expressed as the claim kinds that must be
# supported. Absence of a required kind means the evidence cannot ground that
# layer, so it is declined rather than padded.
SUBSTANTIVE_KINDS = frozenset(
    {ClaimKind.RESULT, ClaimKind.OBSERVATION, ClaimKind.METHOD}
)


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
    """Choose the depths the evidence can honestly support.

    Eligibility is decided per required element, so a layer is declined for a
    named missing element rather than produced from thin material. The reasons
    are diagnostic: the same element missing repeatedly points at a retrieval
    gap, not a generation failure.
    """

    if packet is None or not packet.claims:
        reason = "no supported evidence claims"
        return ExplanationPlan(
            story_id=story.story_id,
            evidence_packet_id=packet.packet_id if packet else None,
            depths=(),
            skipped_reasons=dict.fromkeys(ExplanationDepth, reason),
        )

    kinds = {claim.kind for claim in packet.claims}
    depths: list[ExplanationDepth] = []
    skipped: dict[ExplanationDepth, str] = {}

    # Glance needs something to have happened. Its essential qualification may
    # come from a claim or from source metadata such as preprint status.
    if kinds & SUBSTANTIVE_KINDS:
        depths.append(ExplanationDepth.GLANCE)
    else:
        skipped[ExplanationDepth.GLANCE] = (
            "no result, observation, or method claim to explain"
        )

    # Explain answers how it works, so mechanism is the one hard requirement.
    # Evidence and comparison are covered when supported and omitted otherwise.
    # The qualification Explain must carry may come from source metadata, so it
    # constrains the text without gating whether Explain exists.
    if ExplanationDepth.GLANCE not in depths:
        skipped[ExplanationDepth.EXPLAIN] = "no orientation to expand"
    elif packet.text_sufficiency is AccessClass.METADATA_ONLY:
        skipped[ExplanationDepth.EXPLAIN] = "metadata-only evidence is insufficient"
    elif ClaimKind.METHOD not in kinds:
        skipped[ExplanationDepth.EXPLAIN] = (
            "evidence lacks mechanism; nothing to explain how it works"
        )
    else:
        depths.append(ExplanationDepth.EXPLAIN)

    # Technical inspects the work itself, so it needs primary material and
    # enough accessible text to cite sections, figures, and tables.
    if not story.has_primary_material:
        skipped[ExplanationDepth.TECHNICAL] = "story has no primary material"
    elif packet.text_sufficiency is not AccessClass.OPEN_FULL_TEXT:
        skipped[ExplanationDepth.TECHNICAL] = "open primary text is unavailable"
    elif ExplanationDepth.EXPLAIN not in depths:
        skipped[ExplanationDepth.TECHNICAL] = (
            "no orientation established to go deeper from"
        )
    elif ClaimKind.RESULT not in kinds:
        skipped[ExplanationDepth.TECHNICAL] = "evidence lacks reported results"
    else:
        depths.append(ExplanationDepth.TECHNICAL)

    return ExplanationPlan(
        story_id=story.story_id,
        evidence_packet_id=packet.packet_id,
        depths=tuple(depths),
        skipped_reasons=skipped,
    )
