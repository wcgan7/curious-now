from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from curious_now_v2.db.generation import PendingStory
from curious_now_v2.pipeline.scheduled_cycle import (
    calculate_generation_budget,
    select_generation_batch,
)


def story(
    source: str,
    *,
    accessible: bool,
    age: int,
) -> PendingStory:
    return PendingStory(
        story_id=uuid4(),
        item_id=uuid4(),
        source_name=source,
        content_type="news" if accessible else "peer_reviewed",
        title=f"Story {source} {age}",
        text="evidence " * 200,
        text_sufficiency="open_full_text",
        is_primary_material=not accessible,
        is_accessible_material=accessible,
        published_at=datetime(2026, 8, 11, tzinfo=UTC) - timedelta(days=age),
    )


def test_budget_accrues_through_the_utc_day() -> None:
    budget = calculate_generation_budget(
        now=datetime(2026, 8, 11, 12, tzinfo=UTC),
        daily_usd=20,
        spent_usd=4,
    )
    assert budget.accrued_usd == 10
    assert budget.available_usd == 6


def test_budget_never_refunds_overspend() -> None:
    budget = calculate_generation_budget(
        now=datetime(2026, 8, 11, 23, tzinfo=UTC),
        daily_usd=20,
        spent_usd=21,
    )
    assert budget.available_usd == 0


def test_generation_batch_reserves_one_third_for_accessible_work() -> None:
    candidates = tuple(
        [story(f"paper-{index}", accessible=False, age=index) for index in range(8)]
        + [story(f"news-{index}", accessible=True, age=index) for index in range(5)]
    )
    selected = select_generation_batch(candidates, limit=9)
    assert len(selected) == 9
    assert sum(item.is_accessible_material for item in selected) == 3


def test_generation_batch_spreads_a_dominant_source() -> None:
    candidates = tuple(
        [story("large", accessible=False, age=index) for index in range(5)]
        + [story("small-a", accessible=False, age=1)]
        + [story("small-b", accessible=False, age=2)]
    )
    selected = select_generation_batch(candidates, limit=3, accessible_fraction=0)
    assert {item.source_name for item in selected} == {"large", "small-a", "small-b"}


@pytest.mark.parametrize("accessible", [True, False])
def test_generation_batch_fills_from_whichever_lane_has_work(accessible: bool) -> None:
    candidates = tuple(
        story(f"source-{index}", accessible=accessible, age=index)
        for index in range(5)
    )
    assert len(select_generation_batch(candidates, limit=4)) == 4
