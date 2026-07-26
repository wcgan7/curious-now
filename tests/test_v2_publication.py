from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from curious_now_v2.core.enums import (
    AccessClass,
    ClaimKind,
    ContentType,
    ExplanationDepth,
    ExplanationStatus,
    SourceRole,
    StoryItemRole,
)
from curious_now_v2.core.models import (
    EvidenceClaim,
    EvidencePacket,
    EvidenceSupport,
    Explanation,
    SourceItem,
    StoryDraft,
)
from curious_now_v2.pipeline.explanation_plan import plan_explanations
from curious_now_v2.pipeline.publication import (
    PublicationMode,
    evaluate_publication,
)
from curious_now_v2.pipeline.reader_projection import (
    StoryNotPublishableError,
    project_story,
)

NOW = datetime(2026, 7, 26, 8, tzinfo=UTC)


def make_item(
    *,
    item_id: UUID | None = None,
    source_name: str = "Example Journal",
    source_role: SourceRole = SourceRole.PRIMARY_RESEARCH,
    content_type: ContentType = ContentType.PEER_REVIEWED,
    access_class: AccessClass = AccessClass.ABSTRACT,
) -> SourceItem:
    return SourceItem(
        item_id=item_id or uuid4(),
        source_id=uuid4(),
        source_name=source_name,
        source_role=source_role,
        role=StoryItemRole.PRIMARY_EVIDENCE,
        title="A measured scientific result",
        url="https://example.test/research/result",
        content_type=content_type,
        access_class=access_class,
        published_at=NOW,
        paper_id=uuid4() if content_type is ContentType.PEER_REVIEWED else None,
    )


def make_packet(
    *,
    story_id: UUID,
    item_id: UUID,
    packet_id: UUID,
    access_class: AccessClass = AccessClass.ABSTRACT,
) -> EvidencePacket:
    return EvidencePacket(
        packet_id=packet_id,
        story_id=story_id,
        version=1,
        text_sufficiency=access_class,
        central_claim="The measured effect increased.",
        claims=(
            EvidenceClaim(
                kind=ClaimKind.RESULT,
                text="The measured effect increased.",
                confidence=0.82,
                supports=(
                    EvidenceSupport(
                        item_id=item_id,
                        excerpt="The measured effect increased by 12%.",
                        locator={"section": "Results"},
                    ),
                ),
            ),
        ),
        limitations=("This is an initial study.",),
        created_at=NOW,
    )


def make_explanation(
    *,
    story_id: UUID,
    packet_id: UUID,
    depth: ExplanationDepth = ExplanationDepth.GLANCE,
    created_at: datetime = NOW,
) -> Explanation:
    return Explanation(
        story_id=story_id,
        evidence_packet_id=packet_id,
        depth=depth,
        status=ExplanationStatus.VALID,
        plain_text="The study found a modest increase.",
        prompt_version="v2.1",
        model_provider="test",
        model_name="deterministic",
        created_at=created_at,
    )


def test_story_publishes_when_ai_has_not_run() -> None:
    item = make_item()
    story = StoryDraft(
        story_id=uuid4(),
        canonical_title=item.title,
        items=(item,),
    )

    decision = evaluate_publication(story)

    assert decision.publish is True
    assert decision.mode is PublicationMode.EVIDENCE_ONLY
    assert decision.available_depths == ()


def test_only_current_supported_explanations_are_displayed() -> None:
    item = make_item()
    story_id = uuid4()
    packet_id = uuid4()
    stale_packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        canonical_title=item.title,
        items=(item,),
        current_evidence_packet_id=packet_id,
    )
    packet = make_packet(
        story_id=story_id,
        item_id=item.item_id,
        packet_id=packet_id,
    )
    stale = make_explanation(
        story_id=story_id,
        packet_id=stale_packet_id,
        depth=ExplanationDepth.TECHNICAL,
    )
    current = make_explanation(
        story_id=story_id,
        packet_id=packet_id,
        depth=ExplanationDepth.GLANCE,
    )

    decision = evaluate_publication(
        story,
        packet=packet,
        explanations=(stale, current),
    )

    assert decision.mode is PublicationMode.ENRICHED
    assert decision.available_depths == (ExplanationDepth.GLANCE,)


def test_packet_citing_an_item_outside_the_story_is_blocked() -> None:
    item = make_item()
    story_id = uuid4()
    packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        canonical_title=item.title,
        items=(item,),
        current_evidence_packet_id=packet_id,
    )
    packet = make_packet(
        story_id=story_id,
        item_id=uuid4(),
        packet_id=packet_id,
    )

    decision = evaluate_publication(story, packet=packet)

    assert decision.publish is False
    assert decision.mode is PublicationMode.BLOCKED
    assert decision.reasons == ("evidence packet cites items outside the story",)


def test_non_current_packet_is_blocked() -> None:
    item = make_item()
    story_id = uuid4()
    packet = make_packet(
        story_id=story_id,
        item_id=item.item_id,
        packet_id=uuid4(),
    )
    story = StoryDraft(
        story_id=story_id,
        canonical_title=item.title,
        items=(item,),
        current_evidence_packet_id=uuid4(),
    )

    with pytest.raises(StoryNotPublishableError, match="not the story's current"):
        project_story(story, packet=packet)


@pytest.mark.parametrize(
    ("access_class", "expected"),
    [
        (
            AccessClass.METADATA_ONLY,
            (ExplanationDepth.GLANCE,),
        ),
        (
            AccessClass.ABSTRACT,
            (ExplanationDepth.GLANCE, ExplanationDepth.EXPLAIN),
        ),
        (
            AccessClass.OPEN_FULL_TEXT,
            (
                ExplanationDepth.GLANCE,
                ExplanationDepth.EXPLAIN,
                ExplanationDepth.TECHNICAL,
            ),
        ),
    ],
)
def test_primary_research_depths_follow_text_sufficiency(
    access_class: AccessClass,
    expected: tuple[ExplanationDepth, ...],
) -> None:
    item = make_item(access_class=access_class)
    story_id = uuid4()
    packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        canonical_title=item.title,
        items=(item,),
        current_evidence_packet_id=packet_id,
    )
    packet = make_packet(
        story_id=story_id,
        item_id=item.item_id,
        packet_id=packet_id,
        access_class=access_class,
    )

    plan = plan_explanations(story, packet)

    assert plan.depths == expected


def test_full_text_announcement_does_not_get_a_technical_explanation() -> None:
    item = make_item(
        source_name="Research Lab",
        source_role=SourceRole.LAB_ANNOUNCEMENT,
        content_type=ContentType.LAB_ANNOUNCEMENT,
        access_class=AccessClass.OPEN_FULL_TEXT,
    )
    story_id = uuid4()
    packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        canonical_title=item.title,
        items=(item,),
        current_evidence_packet_id=packet_id,
    )
    packet = make_packet(
        story_id=story_id,
        item_id=item.item_id,
        packet_id=packet_id,
        access_class=AccessClass.OPEN_FULL_TEXT,
    )

    plan = plan_explanations(story, packet)

    assert plan.depths == (
        ExplanationDepth.GLANCE,
        ExplanationDepth.EXPLAIN,
    )
    assert plan.skipped_reasons[ExplanationDepth.TECHNICAL] == (
        "story has no primary research"
    )


def test_reader_projection_keeps_citations_and_latest_explanation() -> None:
    item = make_item()
    story_id = uuid4()
    packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        canonical_title=item.title,
        items=(item,),
        current_evidence_packet_id=packet_id,
    )
    packet = make_packet(
        story_id=story_id,
        item_id=item.item_id,
        packet_id=packet_id,
    )
    older = make_explanation(story_id=story_id, packet_id=packet_id)
    newer = make_explanation(
        story_id=story_id,
        packet_id=packet_id,
        created_at=NOW + timedelta(minutes=1),
    ).model_copy(update={"plain_text": "The newer grounded explanation."})

    read_model = project_story(
        story,
        packet=packet,
        explanations=(newer, older),
    )

    assert read_model.mode == "enriched"
    assert read_model.claims[0].citations[0].url == item.url
    assert read_model.explanations[0].plain_text == "The newer grounded explanation."
