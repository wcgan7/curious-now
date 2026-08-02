from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import exp

import pytest

from curious_now_v2.pipeline.scoring import (
    FRESHNESS_HALF_LIFE_HOURS,
    score_story,
)

WHEN = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def key(rungs: int, significance: str, published: datetime = WHEN) -> datetime:
    return score_story(
        published_at=published, rungs_earned=rungs, significance=significance
    ).effective_at


# --- the property the whole design rests on ---------------------------------


# Stops at a year on purpose. Past roughly 532 days the LIVE score underflows
# exp(-age/h) to zero and ties every story together, so beyond that there is no
# correct live ordering left to agree with -- see the underflow test below,
# which is the point rather than an exception to it.
@pytest.mark.parametrize("hours_later", [0, 1, 24, 24 * 30, 24 * 365])
def test_the_stored_key_orders_exactly_as_the_live_score(hours_later: int) -> None:
    """The clock term cancels, so the ordering must never drift."""

    stories = [
        (rungs, significance, WHEN - timedelta(hours=age))
        for rungs in (1, 2, 3)
        for significance in ("changes_practice", "incremental", "unclear")
        for age in (0, 5, 19, 60, 300)
    ]
    now = WHEN + timedelta(hours=hours_later)

    def live(entry: tuple[int, str, datetime]) -> float:
        rungs, significance, published = entry
        scored = score_story(
            published_at=published, rungs_earned=rungs, significance=significance
        )
        age = (now - published) / timedelta(hours=1)
        return scored.quality * exp(-age / FRESHNESS_HALF_LIFE_HOURS)

    by_live = sorted(stories, key=lambda e: (-live(e), str(e)))
    by_key = sorted(stories, key=lambda e: (-key(e[0], e[1], e[2]).timestamp(), str(e)))

    assert by_live == by_key


def test_the_key_does_not_underflow_where_the_live_score_does() -> None:
    """exp(-age/h) reaches 0.0 in double precision at about 745 half-lives.

    Where that falls depends on the half-life -- 532 days at 18 hours, and
    about 13 years at a week -- so it is derived rather than written down. Log
    space has no such limit at any horizon.
    """

    underflow_hours = 760 * FRESHNESS_HALF_LIFE_HOURS
    ancient = WHEN - timedelta(hours=underflow_hours)

    assert exp(-underflow_hours / FRESHNESS_HALF_LIFE_HOURS) == 0.0
    assert key(3, "changes_practice", ancient) > key(1, "unclear", ancient)


# --- ordering ---------------------------------------------------------------


def test_significance_outweighs_rungs() -> None:
    """Whether it mattered beats how well we could explain it."""

    assert key(1, "changes_practice") > key(3, "unclear")


def test_more_rungs_win_at_equal_significance() -> None:
    assert key(3, "incremental") > key(2, "incremental") > key(1, "incremental")


def test_a_perfect_story_pays_nothing() -> None:
    assert key(3, "changes_practice") == WHEN


def test_every_shortcoming_costs_time_never_gains_it() -> None:
    for rungs in (1, 2, 3):
        for significance in ("changes_practice", "incremental", "unclear"):
            assert key(rungs, significance) <= WHEN


def test_quality_is_worth_roughly_a_fortnight_of_age() -> None:
    """The spread has to reach across the corpus or quality is decoration.

    At an 18-hour half-life it was worth 33 hours against a corpus spanning
    months, and the age bands did not overlap at all: a three-rung
    practice-changing paper sat below every two-day-old story whatever it said.
    """

    penalty = WHEN - key(1, "unclear")

    assert timedelta(days=11) < penalty < timedelta(days=15)


def test_quality_can_outrank_several_days_of_freshness() -> None:
    """The concrete claim: the best beats routine work published days later."""

    best_today = key(3, "changes_practice", WHEN - timedelta(days=4))
    routine_now = key(3, "incremental", WHEN)

    assert best_today > routine_now


# --- unknown values ---------------------------------------------------------


def test_an_unknown_verdict_is_treated_as_unclear_not_as_good() -> None:
    assert key(3, "not_a_verdict") == key(3, "unclear")


def test_an_unexpected_rung_count_does_not_earn_a_bonus() -> None:
    assert key(9, "incremental") == key(1, "incremental")


def test_reasons_are_stated_in_hours() -> None:
    scored = score_story(
        published_at=WHEN, rungs_earned=2, significance="incremental"
    )

    assert any("rungs 2" in reason and "h)" in reason for reason in scored.reasons)
    assert any("significance incremental" in reason for reason in scored.reasons)
