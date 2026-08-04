"""Whose turn it is, when several stories share a key.

Kept apart from the rest of the ranking tests because `queue_positions` needs
no database: it decides the order of a tie from values already in hand. Those
tests carry a module-level skip when no database URL is set, which would have
hidden these in CI -- and the property they protect, that a story's position
never moves once assigned, is exactly the one worth protecting there.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from curious_now_v2.db.ranking import RankingInput, queue_positions
from curious_now_v2.pipeline.scoring import score_story

# --- whose turn it is -------------------------------------------------------


def _input(story_id: str, source: str, seen_days: int, published: datetime = None):
    return RankingInput(
        story_id=UUID(story_id),
        published_at=published or datetime(2026, 7, 31, 4, 0, tzinfo=UTC),
        rungs=3,
        significance="changes_practice",
        source_name=source,
        first_seen=datetime(2026, 7, 31, 4, 0, tzinfo=UTC) + timedelta(days=seen_days),
    )


def _id(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def test_a_sources_queue_runs_oldest_first() -> None:
    positions = queue_positions(
        [
            _input(_id(2), "arXiv machine learning", seen_days=2),
            _input(_id(1), "arXiv machine learning", seen_days=1),
            _input(_id(3), "arXiv machine learning", seen_days=3),
        ]
    )
    assert positions[UUID(_id(1))] == 0
    assert positions[UUID(_id(2))] == 1
    assert positions[UUID(_id(3))] == 2


def test_each_source_gets_its_own_queue() -> None:
    """Which is the whole point: three sources tied on a key each start at
    zero, so reading the column walks them one apiece rather than one
    publisher's whole day and then the next."""

    positions = queue_positions(
        [
            _input(_id(1), "arXiv machine learning", seen_days=1),
            _input(_id(2), "eLife", seen_days=1),
            _input(_id(3), "NASA", seen_days=1),
            _input(_id(4), "arXiv machine learning", seen_days=2),
        ]
    )
    assert positions[UUID(_id(1))] == 0
    assert positions[UUID(_id(2))] == 0
    assert positions[UUID(_id(3))] == 0
    assert positions[UUID(_id(4))] == 1


def test_stories_on_different_keys_do_not_share_a_queue() -> None:
    """A queue exists to break a tie. Stories that were never tied must each
    keep position zero, or the term would start shifting things it has no
    business shifting."""

    positions = queue_positions(
        [
            _input(_id(1), "eLife", seen_days=1),
            _input(
                _id(2),
                "eLife",
                seen_days=1,
                published=datetime(2026, 7, 30, 4, 0, tzinfo=UTC),
            ),
        ]
    )
    assert positions[UUID(_id(1))] == 0
    assert positions[UUID(_id(2))] == 0


def test_a_later_arrival_never_moves_an_earlier_one() -> None:
    """The key is written once when a story is published, and that is the
    property the whole design rests on. A story joining a queue must take the
    back of it, leaving every position already assigned untouched."""

    existing = [
        _input(_id(1), "eLife", seen_days=1),
        _input(_id(2), "eLife", seen_days=2),
    ]
    before = queue_positions(existing)
    after = queue_positions([*existing, _input(_id(3), "eLife", seen_days=3)])

    assert after[UUID(_id(1))] == before[UUID(_id(1))]
    assert after[UUID(_id(2))] == before[UUID(_id(2))]
    assert after[UUID(_id(3))] == 2


def test_quality_still_decides_across_queues() -> None:
    """A story at the back of a long queue must still outrank a worse story
    published the same day. If it does not, the rotation has overtaken the
    thing it was only ever meant to tie-break."""

    best_but_hundredth = score_story(
        published_at=datetime(2026, 7, 31, 4, 0, tzinfo=UTC),
        rungs_earned=3,
        significance="changes_practice",
        queue_position=100,
    )
    worse_but_first = score_story(
        published_at=datetime(2026, 7, 31, 4, 0, tzinfo=UTC),
        rungs_earned=2,
        significance="incremental",
    )
    assert best_but_hundredth.effective_at > worse_but_first.effective_at
