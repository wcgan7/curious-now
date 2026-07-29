from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from curious_now_v2.core.enums import (
    ExplanationDepth,
    ExplanationStatus,
    ReaderTitleKind,
    StoryItemRole,
)
from curious_now_v2.core.models import (
    EvidencePacket,
    Explanation,
    ReaderTitle,
    StoryDraft,
)
from curious_now_v2.pipeline.explanation_plan import plan_explanations

DEPTH_ORDER = (
    ExplanationDepth.GLANCE,
    ExplanationDepth.EXPLAIN,
    ExplanationDepth.TECHNICAL,
)


class PublicationMode(StrEnum):
    BLOCKED = "blocked"
    EVIDENCE_ONLY = "evidence_only"
    ENRICHED = "enriched"


class PresentationSet(BaseModel):
    """One packet version's displayable explanations, from a single spine."""

    model_config = ConfigDict(frozen=True)

    packet_id: UUID
    spine_id: UUID | None
    depths: tuple[ExplanationDepth, ...]
    complete: bool


class PublicationDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    publish: bool
    mode: PublicationMode
    reasons: tuple[str, ...]
    reader_title: ReaderTitle | None
    visible_item_ids: tuple[UUID, ...]
    display_packet_id: UUID | None
    display_spine_id: UUID | None
    available_depths: tuple[ExplanationDepth, ...]


def resolve_reader_title(story: StoryDraft) -> ReaderTitle | None:
    """Apply the title fallback order from the presentation contract.

    A valid generated display title wins; otherwise a source title is shown
    with attribution, because a source's own headline is an attributed fact
    rather than editorial text.
    """

    display = story.current_display_title
    if (
        display is not None
        and display.status is ExplanationStatus.VALID
        and display.text.strip()
    ):
        return ReaderTitle(
            text=display.text.strip(),
            kind=ReaderTitleKind.DISPLAY,
        )

    primary = next(
        (
            item
            for item in story.items
            if item.role is StoryItemRole.PRIMARY_EVIDENCE and item.title.strip()
        ),
        None,
    )
    if primary is not None:
        return ReaderTitle(
            text=primary.title.strip(),
            kind=ReaderTitleKind.SOURCE,
            attribution=primary.source_name,
        )

    if story.working_title.strip():
        return ReaderTitle(
            text=story.working_title.strip(),
            kind=ReaderTitleKind.WORKING,
        )

    fallback = next((item for item in story.items if item.title.strip()), None)
    if fallback is not None:
        return ReaderTitle(
            text=fallback.title.strip(),
            kind=ReaderTitleKind.SOURCE,
            attribution=fallback.source_name,
        )
    return None


def select_presentation_set(
    story: StoryDraft,
    *,
    packets: tuple[EvidencePacket, ...] = (),
    explanations: tuple[Explanation, ...] = (),
) -> PresentationSet | None:
    """Choose the packet version whose validated explanations the reader shows.

    The newest packet version with a complete validated set wins; a newer
    packet whose presentations are not yet validated does not withdraw the
    previous valid set. Explanations from different spine versions of one
    packet are never mixed.
    """

    candidates: list[PresentationSet] = []
    ordered_packets = sorted(
        (packet for packet in packets if packet.story_id == story.story_id),
        key=lambda packet: packet.version,
        reverse=True,
    )
    for packet in ordered_packets:
        planned = frozenset(plan_explanations(story, packet).depths)
        if not planned:
            continue
        valid = [
            explanation
            for explanation in explanations
            if explanation.status is ExplanationStatus.VALID
            and explanation.story_id == story.story_id
            and explanation.evidence_packet_id == packet.packet_id
            and explanation.depth in planned
        ]
        if not valid:
            continue

        spine_groups: dict[UUID | None, list[Explanation]] = {}
        for explanation in valid:
            spine_groups.setdefault(explanation.conceptual_spine_id, []).append(
                explanation
            )
        spine_id, group = max(
            spine_groups.items(),
            key=lambda entry: (
                len({explanation.depth for explanation in entry[1]}),
                max(explanation.created_at for explanation in entry[1]),
            ),
        )
        depths = tuple(
            sorted(
                {explanation.depth for explanation in group},
                key=DEPTH_ORDER.index,
            )
        )
        candidates.append(
            PresentationSet(
                packet_id=packet.packet_id,
                spine_id=spine_id,
                depths=depths,
                complete=set(depths) >= planned,
            )
        )

    if not candidates:
        return None
    complete = [candidate for candidate in candidates if candidate.complete]
    return complete[0] if complete else candidates[0]


def evaluate_publication(
    story: StoryDraft,
    *,
    packets: tuple[EvidencePacket, ...] = (),
    explanations: tuple[Explanation, ...] = (),
) -> PublicationDecision:
    """Return the reader mode without making AI a publication gate."""

    visible_item_ids = tuple(item.item_id for item in story.items if item.url.strip())
    reader_title = resolve_reader_title(story)

    def blocked(reason: str) -> PublicationDecision:
        return PublicationDecision(
            publish=False,
            mode=PublicationMode.BLOCKED,
            reasons=(reason,),
            reader_title=reader_title,
            visible_item_ids=visible_item_ids,
            display_packet_id=None,
            display_spine_id=None,
            available_depths=(),
        )

    if reader_title is None:
        return blocked("story has no usable title")
    if not visible_item_ids:
        return blocked("story has no visible source links")

    for packet in packets:
        if packet.story_id != story.story_id:
            return blocked("evidence packet belongs to another story")
        if packet.cited_item_ids - story.item_ids:
            return blocked("evidence packet cites items outside the story")

    selection = select_presentation_set(
        story,
        packets=packets,
        explanations=explanations,
    )
    if selection is None:
        return PublicationDecision(
            publish=True,
            mode=PublicationMode.EVIDENCE_ONLY,
            reasons=("no validated explanation set; publish sources",),
            reader_title=reader_title,
            visible_item_ids=visible_item_ids,
            display_packet_id=None,
            display_spine_id=None,
            available_depths=(),
        )

    return PublicationDecision(
        publish=True,
        mode=PublicationMode.ENRICHED,
        reasons=("validated evidence-backed explanations are available",),
        reader_title=reader_title,
        visible_item_ids=visible_item_ids,
        display_packet_id=selection.packet_id,
        display_spine_id=selection.spine_id,
        available_depths=selection.depths,
    )
