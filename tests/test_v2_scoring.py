from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import exp

import pytest

from curious_now_v2.pipeline.scoring import (
    FRESHNESS_HALF_LIFE_HOURS,
    QUALITY_BY_RUNGS,
    QUALITY_BY_SIGNIFICANCE,
    ROTATION_SECONDS,
    SOURCE_DENSITY_STRENGTH,
    completion_rungs,
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


def test_a_tie_is_broken_by_queue_position_and_only_by_a_second() -> None:
    """Two stories that earned the same thing on the same day must not tie.

    Left tied, the order fell to the row UUID, which put 110 stories from one
    publisher at the top of the feed in an order that meant nothing.
    """

    first = score_story(
        published_at=WHEN, rungs_earned=3, significance="changes_practice"
    )
    second = score_story(
        published_at=WHEN,
        rungs_earned=3,
        significance="changes_practice",
        queue_position=1,
    )
    assert second.effective_at < first.effective_at
    assert (first.effective_at - second.effective_at).total_seconds() == pytest.approx(
        ROTATION_SECONDS
    )


def test_the_tie_break_cannot_overturn_a_quality_decision() -> None:
    """The whole rotation must stay inside the narrowest quality gap.

    A minute per place was tried first: with the largest observed tie at 101
    stories it cleared the closest pair of quality bands by 1.3x, which is not
    a margin. A second clears it by sixty.
    """

    offsets = sorted(
        score_story(
            published_at=WHEN, rungs_earned=rungs, significance=verdict
        ).offset_hours
        for rungs in QUALITY_BY_RUNGS
        for verdict in QUALITY_BY_SIGNIFICANCE
    )
    narrowest_gap = min(b - a for a, b in zip(offsets, offsets[1:]) if b - a > 0)

    # Far beyond any tie we have seen; the largest was 101.
    largest_rotation_hours = 500 * ROTATION_SECONDS / 3600
    assert largest_rotation_hours < narrowest_gap


def test_position_zero_is_the_same_key_as_no_position_at_all() -> None:
    """So that adding the term did not silently shift every existing story."""

    assert score_story(
        published_at=WHEN, rungs_earned=2, significance="incremental"
    ).effective_at == score_story(
        published_at=WHEN,
        rungs_earned=2,
        significance="incremental",
        queue_position=0,
    ).effective_at


def test_the_tie_break_is_not_reported_as_a_shortcoming() -> None:
    """It is whose turn it is, not a judgement, and the reasons say so.

    `offset_hours` and `quality` are what an operator reads to learn why one
    story sits above another. A fraction of a second is not an answer to that
    question, and listing it would imply the story was judged worse.
    """

    plain = score_story(
        published_at=WHEN, rungs_earned=3, significance="changes_practice"
    )
    rotated = score_story(
        published_at=WHEN,
        rungs_earned=3,
        significance="changes_practice",
        queue_position=40,
    )
    assert rotated.reasons == plain.reasons
    assert rotated.quality == plain.quality
    assert rotated.offset_hours == plain.offset_hours


def test_a_negative_position_cannot_promote_a_story() -> None:
    assert (
        score_story(
            published_at=WHEN,
            rungs_earned=3,
            significance="changes_practice",
            queue_position=-5,
        ).effective_at
        <= WHEN
    )


def test_first_story_in_a_source_category_day_pays_no_density_cost() -> None:
    plain = score_story(
        published_at=WHEN, rungs_earned=3, significance="changes_practice"
    )
    first = score_story(
        published_at=WHEN,
        rungs_earned=3,
        significance="changes_practice",
        density_position=0,
    )

    assert first.effective_at == plain.effective_at
    assert first.density_factor == 1.0
    assert first.density_offset_hours == 0.0


def test_density_cost_grows_smoothly_without_changing_quality() -> None:
    first = score_story(
        published_at=WHEN, rungs_earned=3, significance="changes_practice"
    )
    second = score_story(
        published_at=WHEN,
        rungs_earned=3,
        significance="changes_practice",
        density_position=1,
    )
    third = score_story(
        published_at=WHEN,
        rungs_earned=3,
        significance="changes_practice",
        density_position=2,
    )

    assert second.density_factor == pytest.approx(
        1 / (1 + SOURCE_DENSITY_STRENGTH)
    )
    assert first.effective_at > second.effective_at > third.effective_at
    assert (first.effective_at - second.effective_at).total_seconds() == pytest.approx(
        timedelta(hours=16.01).total_seconds(), abs=60
    )
    assert second.quality == first.quality
    assert second.offset_hours == first.offset_hours
    assert second.reasons == first.reasons


def test_negative_density_position_cannot_promote_a_story() -> None:
    assert score_story(
        published_at=WHEN,
        rungs_earned=3,
        significance="changes_practice",
        density_position=-5,
    ).effective_at == WHEN


@pytest.mark.parametrize(
    ("valid", "eligible", "band"),
    [(1, 1, 3), (2, 2, 3), (3, 3, 3), (2, 3, 2), (1, 2, 2), (1, 3, 1)],
)
def test_completion_is_relative_to_eligible_depths(
    valid: int, eligible: int, band: int
) -> None:
    assert completion_rungs(valid_depths=valid, eligible_depths=eligible) == band
