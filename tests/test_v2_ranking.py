from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from curious_now_v2.core.enums import (
    AccessClass,
    ContentType,
    SourceRole,
    StoryItemRole,
)
from curious_now_v2.core.models import SourceItem, StoryDraft
from curious_now_v2.pipeline.ranking import rank_stories, score_story

NOW = datetime(2026, 7, 29, 12, tzinfo=UTC)


def make_story(
    *,
    story_id: UUID | None = None,
    source_name: str = "Example Journal",
    source_role: SourceRole = SourceRole.PRIMARY_RESEARCH,
    content_type: ContentType = ContentType.PEER_REVIEWED,
    access_class: AccessClass = AccessClass.ABSTRACT,
    published_at: datetime | None = NOW,
    extra_items: tuple[SourceItem, ...] = (),
) -> StoryDraft:
    item = SourceItem(
        item_id=uuid4(),
        source_id=uuid4(),
        source_name=source_name,
        source_role=source_role,
        role=StoryItemRole.PRIMARY_EVIDENCE,
        title="A measured scientific result",
        url="https://example.test/result",
        content_type=content_type,
        access_class=access_class,
        published_at=published_at,
    )
    return StoryDraft(
        story_id=story_id or uuid4(),
        working_title=item.title,
        items=(item, *extra_items),
    )


def make_coverage_item(source_name: str) -> SourceItem:
    return SourceItem(
        item_id=uuid4(),
        source_id=uuid4(),
        source_name=source_name,
        source_role=SourceRole.JOURNALISM,
        role=StoryItemRole.INDEPENDENT_COVERAGE,
        title=f"{source_name} covers the result",
        url=f"https://example.test/{source_name}",
        content_type=ContentType.NEWS,
        access_class=AccessClass.SNIPPET,
        published_at=NOW,
    )


def test_fresh_stories_outrank_old_ones() -> None:
    fresh = make_story(published_at=NOW)
    old = make_story(published_at=NOW - timedelta(days=4))

    assert score_story(fresh, now=NOW).score > score_story(old, now=NOW).score


def test_peer_reviewed_outranks_a_press_release_of_the_same_age() -> None:
    reviewed = make_story(content_type=ContentType.PEER_REVIEWED)
    press = make_story(
        source_name="Corp Comms",
        source_role=SourceRole.PRESS_RELEASE,
        content_type=ContentType.PRESS_RELEASE,
    )

    assert score_story(reviewed, now=NOW).score > score_story(press, now=NOW).score


def test_independent_corroboration_raises_the_score() -> None:
    alone = make_story()
    corroborated = make_story(
        extra_items=(
            make_coverage_item("Science News"),
            make_coverage_item("Quanta"),
        ),
    )

    assert (
        score_story(corroborated, now=NOW).score > score_story(alone, now=NOW).score
    )


def test_interested_party_only_story_is_penalized() -> None:
    lab_only = make_story(
        source_name="A Lab",
        source_role=SourceRole.LAB_ANNOUNCEMENT,
        content_type=ContentType.LAB_ANNOUNCEMENT,
    )

    ranked = score_story(lab_only, now=NOW)

    assert "only interested-party sources" in ranked.reasons


def test_reasons_are_recorded_for_every_signal() -> None:
    ranked = score_story(make_story(), now=NOW)

    assert len(ranked.reasons) == 5
    assert any("published" in reason for reason in ranked.reasons)
    assert any("evidence type" in reason for reason in ranked.reasons)


def test_variety_damper_breaks_up_a_single_source_flood() -> None:
    flood = tuple(make_story(source_name="arXiv AI") for _ in range(8))
    others = (
        make_story(source_name="Nature"),
        make_story(source_name="Science News"),
    )

    ranked = rank_stories((*flood, *others), now=NOW)
    top_sources = [entry.principal_source for entry in ranked[:3]]

    # Without damping all eight arXiv stories would precede the others.
    assert len(set(top_sources)) > 1
    assert "Nature" in top_sources or "Science News" in top_sources


def test_variety_damper_records_its_reason() -> None:
    stories = tuple(make_story(source_name="arXiv AI") for _ in range(3))

    ranked = rank_stories(stories, now=NOW)
    damped = [
        entry
        for entry in ranked
        if any("variety damper" in reason for reason in entry.reasons)
    ]

    assert len(damped) == 2
    assert all(entry.variety_factor < 1 for entry in damped)


def test_first_story_from_a_source_is_not_damped() -> None:
    stories = (
        make_story(source_name="Nature"),
        make_story(source_name="arXiv AI"),
    )

    ranked = rank_stories(stories, now=NOW)

    assert all(entry.variety_factor == 1.0 for entry in ranked)


def test_ranking_is_deterministic() -> None:
    stories = tuple(
        make_story(source_name=name)
        for name in ("arXiv AI", "Nature", "arXiv AI", "STAT")
    )

    first = rank_stories(stories, now=NOW)
    second = rank_stories(stories, now=NOW)

    assert [entry.story_id for entry in first] == [
        entry.story_id for entry in second
    ]


def test_missing_publication_date_does_not_crash_ranking() -> None:
    ranked = score_story(make_story(published_at=None), now=NOW)

    assert ranked.score > 0
    assert "no publication date; assumed mid-freshness" in ranked.reasons
