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
    ReaderTitleKind,
    SourceRole,
    StoryItemRole,
)
from curious_now_v2.core.models import (
    DisplayTitle,
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
    version: int = 1,
    access_class: AccessClass = AccessClass.ABSTRACT,
) -> EvidencePacket:
    return EvidencePacket(
        packet_id=packet_id,
        story_id=story_id,
        version=version,
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
    spine_id: UUID | None = None,
    depth: ExplanationDepth = ExplanationDepth.GLANCE,
    created_at: datetime = NOW,
) -> Explanation:
    return Explanation(
        story_id=story_id,
        evidence_packet_id=packet_id,
        conceptual_spine_id=spine_id,
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
        working_title=item.title,
        items=(item,),
    )

    decision = evaluate_publication(story)

    assert decision.publish is True
    assert decision.mode is PublicationMode.EVIDENCE_ONLY
    assert decision.available_depths == ()
    assert decision.display_packet_id is None


def test_explanations_from_unknown_packets_are_ignored() -> None:
    item = make_item()
    story_id = uuid4()
    packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        working_title=item.title,
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
        packet_id=uuid4(),
        depth=ExplanationDepth.TECHNICAL,
    )
    current = make_explanation(
        story_id=story_id,
        packet_id=packet_id,
        depth=ExplanationDepth.GLANCE,
    )

    decision = evaluate_publication(
        story,
        packets=(packet,),
        explanations=(stale, current),
    )

    assert decision.mode is PublicationMode.ENRICHED
    assert decision.available_depths == (ExplanationDepth.GLANCE,)
    assert decision.display_packet_id == packet_id


def test_packet_citing_an_item_outside_the_story_is_blocked() -> None:
    item = make_item()
    story_id = uuid4()
    packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        working_title=item.title,
        items=(item,),
        current_evidence_packet_id=packet_id,
    )
    packet = make_packet(
        story_id=story_id,
        item_id=uuid4(),
        packet_id=packet_id,
    )

    decision = evaluate_publication(story, packets=(packet,))

    assert decision.publish is False
    assert decision.mode is PublicationMode.BLOCKED
    assert decision.reasons == ("evidence packet cites items outside the story",)


def test_newer_unvalidated_packet_does_not_withdraw_previous_valid_set() -> None:
    item = make_item()
    story_id = uuid4()
    old_packet_id = uuid4()
    new_packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        working_title=item.title,
        items=(item,),
        current_evidence_packet_id=new_packet_id,
    )
    old_packet = make_packet(
        story_id=story_id,
        item_id=item.item_id,
        packet_id=old_packet_id,
        version=1,
    )
    new_packet = make_packet(
        story_id=story_id,
        item_id=item.item_id,
        packet_id=new_packet_id,
        version=2,
    )
    old_set = tuple(
        make_explanation(story_id=story_id, packet_id=old_packet_id, depth=depth)
        for depth in (ExplanationDepth.GLANCE, ExplanationDepth.EXPLAIN)
    )

    decision = evaluate_publication(
        story,
        packets=(old_packet, new_packet),
        explanations=old_set,
    )

    assert decision.mode is PublicationMode.ENRICHED
    assert decision.display_packet_id == old_packet_id
    assert decision.available_depths == (
        ExplanationDepth.GLANCE,
        ExplanationDepth.EXPLAIN,
    )


def test_newer_partial_set_does_not_replace_older_complete_set() -> None:
    item = make_item()
    story_id = uuid4()
    old_packet_id = uuid4()
    new_packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        working_title=item.title,
        items=(item,),
        current_evidence_packet_id=new_packet_id,
    )
    packets = (
        make_packet(
            story_id=story_id,
            item_id=item.item_id,
            packet_id=old_packet_id,
            version=1,
        ),
        make_packet(
            story_id=story_id,
            item_id=item.item_id,
            packet_id=new_packet_id,
            version=2,
        ),
    )
    explanations = (
        make_explanation(
            story_id=story_id,
            packet_id=old_packet_id,
            depth=ExplanationDepth.GLANCE,
        ),
        make_explanation(
            story_id=story_id,
            packet_id=old_packet_id,
            depth=ExplanationDepth.EXPLAIN,
        ),
        make_explanation(
            story_id=story_id,
            packet_id=new_packet_id,
            depth=ExplanationDepth.GLANCE,
        ),
    )

    decision = evaluate_publication(
        story,
        packets=packets,
        explanations=explanations,
    )

    assert decision.display_packet_id == old_packet_id
    assert decision.available_depths == (
        ExplanationDepth.GLANCE,
        ExplanationDepth.EXPLAIN,
    )


def test_newest_partial_set_is_used_when_no_complete_set_exists() -> None:
    item = make_item()
    story_id = uuid4()
    packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        working_title=item.title,
        items=(item,),
        current_evidence_packet_id=packet_id,
    )
    packet = make_packet(
        story_id=story_id,
        item_id=item.item_id,
        packet_id=packet_id,
        version=2,
    )
    glance_only = make_explanation(
        story_id=story_id,
        packet_id=packet_id,
        depth=ExplanationDepth.GLANCE,
    )

    decision = evaluate_publication(
        story,
        packets=(packet,),
        explanations=(glance_only,),
    )

    assert decision.mode is PublicationMode.ENRICHED
    assert decision.display_packet_id == packet_id
    assert decision.available_depths == (ExplanationDepth.GLANCE,)


def test_explanations_from_different_spines_are_not_mixed() -> None:
    item = make_item()
    story_id = uuid4()
    packet_id = uuid4()
    spine_a = uuid4()
    spine_b = uuid4()
    story = StoryDraft(
        story_id=story_id,
        working_title=item.title,
        items=(item,),
        current_evidence_packet_id=packet_id,
    )
    packet = make_packet(
        story_id=story_id,
        item_id=item.item_id,
        packet_id=packet_id,
    )
    glance_a = make_explanation(
        story_id=story_id,
        packet_id=packet_id,
        spine_id=spine_a,
        depth=ExplanationDepth.GLANCE,
    )
    explain_b = make_explanation(
        story_id=story_id,
        packet_id=packet_id,
        spine_id=spine_b,
        depth=ExplanationDepth.EXPLAIN,
        created_at=NOW + timedelta(minutes=1),
    )

    decision = evaluate_publication(
        story,
        packets=(packet,),
        explanations=(glance_a, explain_b),
    )

    assert decision.display_spine_id == spine_b
    assert decision.available_depths == (ExplanationDepth.EXPLAIN,)


def test_valid_display_title_wins_the_reader_title() -> None:
    item = make_item()
    story_id = uuid4()
    packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        working_title="internal working label",
        items=(item,),
        current_evidence_packet_id=packet_id,
        current_display_title=DisplayTitle(
            story_id=story_id,
            evidence_packet_id=packet_id,
            version=1,
            text="A measured effect grows in a controlled study",
            status=ExplanationStatus.VALID,
            prompt_version="v2.1",
        ),
    )

    decision = evaluate_publication(story)

    assert decision.reader_title is not None
    assert decision.reader_title.kind is ReaderTitleKind.DISPLAY
    assert decision.reader_title.text == (
        "A measured effect grows in a controlled study"
    )


def test_source_title_fallback_is_attributed() -> None:
    item = make_item()
    story = StoryDraft(
        story_id=uuid4(),
        working_title="internal working label",
        items=(item,),
    )

    decision = evaluate_publication(story)

    assert decision.reader_title is not None
    assert decision.reader_title.kind is ReaderTitleKind.SOURCE
    assert decision.reader_title.text == item.title
    assert decision.reader_title.attribution == item.source_name


def test_invalid_display_title_falls_back_to_a_source_title() -> None:
    item = make_item()
    story_id = uuid4()
    packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        working_title="internal working label",
        items=(item,),
        current_display_title=DisplayTitle(
            story_id=story_id,
            evidence_packet_id=packet_id,
            version=1,
            text="An overhyped rejected title",
            status=ExplanationStatus.INVALID,
            prompt_version="v2.1",
        ),
    )

    decision = evaluate_publication(story)

    assert decision.reader_title is not None
    assert decision.reader_title.kind is ReaderTitleKind.SOURCE
    assert decision.reader_title.text == item.title


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
        working_title=item.title,
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
        working_title=item.title,
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
        "story has no primary material"
    )


def test_full_text_technical_report_is_eligible_for_technical() -> None:
    item = make_item(
        source_name="National Lab",
        source_role=SourceRole.LAB_ANNOUNCEMENT,
        content_type=ContentType.REPORT,
        access_class=AccessClass.OPEN_FULL_TEXT,
    )
    story_id = uuid4()
    packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        working_title=item.title,
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

    assert ExplanationDepth.TECHNICAL in plan.depths


def test_blocked_story_raises_in_projection() -> None:
    item = make_item()
    story_id = uuid4()
    packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        working_title=item.title,
        items=(item,),
        current_evidence_packet_id=packet_id,
    )
    packet = make_packet(
        story_id=story_id,
        item_id=uuid4(),
        packet_id=packet_id,
    )

    with pytest.raises(StoryNotPublishableError, match="outside the story"):
        project_story(story, packets=(packet,))


def test_reader_projection_keeps_citations_and_latest_explanation() -> None:
    item = make_item()
    story_id = uuid4()
    packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        working_title=item.title,
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
        packets=(packet,),
        explanations=(newer, older),
    )

    assert read_model.mode == "enriched"
    assert read_model.title == item.title
    assert read_model.title_kind is ReaderTitleKind.SOURCE
    assert read_model.title_attribution == item.source_name
    assert read_model.claims[0].citations[0].url == item.url
    assert read_model.explanations[0].plain_text == "The newer grounded explanation."


def test_reader_projection_shows_claims_from_the_displayed_packet() -> None:
    item = make_item()
    story_id = uuid4()
    old_packet_id = uuid4()
    new_packet_id = uuid4()
    story = StoryDraft(
        story_id=story_id,
        working_title=item.title,
        items=(item,),
        current_evidence_packet_id=new_packet_id,
    )
    old_packet = make_packet(
        story_id=story_id,
        item_id=item.item_id,
        packet_id=old_packet_id,
        version=1,
    )
    new_packet = make_packet(
        story_id=story_id,
        item_id=item.item_id,
        packet_id=new_packet_id,
        version=2,
    )
    old_set = tuple(
        make_explanation(story_id=story_id, packet_id=old_packet_id, depth=depth)
        for depth in (ExplanationDepth.GLANCE, ExplanationDepth.EXPLAIN)
    )

    read_model = project_story(
        story,
        packets=(old_packet, new_packet),
        explanations=old_set,
    )

    assert read_model.mode == "enriched"
    assert {claim.claim_id for claim in read_model.claims} == {
        claim.claim_id for claim in old_packet.claims
    }
