from __future__ import annotations

from typing import Literal

from curious_now_v2.core.enums import ExplanationStatus
from curious_now_v2.core.models import EvidencePacket, Explanation, StoryDraft
from curious_now_v2.core.read_models import (
    CitationView,
    ClaimView,
    ExplanationView,
    SourceLinkView,
    StoryReadModel,
)
from curious_now_v2.pipeline.publication import PublicationMode, evaluate_publication


class StoryNotPublishableError(ValueError):
    pass


def project_story(
    story: StoryDraft,
    *,
    packet: EvidencePacket | None = None,
    explanations: tuple[Explanation, ...] = (),
) -> StoryReadModel:
    """Build the stable reader contract from validated pipeline records."""

    decision = evaluate_publication(
        story,
        packet=packet,
        explanations=explanations,
    )
    if not decision.publish:
        raise StoryNotPublishableError("; ".join(decision.reasons))

    items_by_id = {item.item_id: item for item in story.items}
    sources = tuple(
        SourceLinkView(
            item_id=item.item_id,
            source_name=item.source_name,
            source_role=item.source_role,
            story_role=item.role,
            title=item.title,
            url=item.url,
            content_type=item.content_type,
            access_class=item.access_class,
            published_at=item.published_at,
        )
        for item in story.items
    )

    claims: tuple[ClaimView, ...] = ()
    if packet is not None:
        claims = tuple(
            ClaimView(
                claim_id=claim.claim_id,
                kind=claim.kind,
                text=claim.text,
                confidence=claim.confidence,
                citations=tuple(
                    CitationView(
                        item_id=support.item_id,
                        source_name=items_by_id[support.item_id].source_name,
                        url=items_by_id[support.item_id].url,
                        excerpt=support.excerpt,
                        locator=support.locator,
                    )
                    for support in claim.supports
                ),
            )
            for claim in packet.claims
        )

    current_explanations = {
        explanation.depth: explanation
        for explanation in sorted(explanations, key=lambda value: value.created_at)
        if explanation.status is ExplanationStatus.VALID
        and explanation.story_id == story.story_id
        and explanation.evidence_packet_id == story.current_evidence_packet_id
        and explanation.depth in decision.available_depths
    }
    explanation_views = tuple(
        ExplanationView(
            depth=depth,
            plain_text=current_explanations[depth].plain_text,
            content=current_explanations[depth].content,
        )
        for depth in decision.available_depths
    )
    mode: Literal["evidence_only", "enriched"] = (
        "enriched"
        if decision.mode is PublicationMode.ENRICHED
        else "evidence_only"
    )

    return StoryReadModel(
        story_id=story.story_id,
        title=story.canonical_title,
        mode=mode,
        sources=sources,
        claims=claims,
        available_depths=decision.available_depths,
        explanations=explanation_views,
    )
