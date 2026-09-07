from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from curious_now_v2.db.ranking import (
    density_identity,
    published_inputs,
    reserve_density_position,
    run_ranking,
)
from curious_now_v2.pipeline.scoring import (
    QUALITY_BY_RUNGS,
    QUALITY_BY_SIGNIFICANCE,
)

DATABASE_URL = os.environ.get("CURIOUS_NOW_V2_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="CURIOUS_NOW_V2_DATABASE_URL is not set"
)


@pytest.fixture
def conn():
    with psycopg.connect(DATABASE_URL) as connection:
        yield connection
        connection.rollback()


def test_the_publication_date_comes_from_the_item_not_the_story(conn) -> None:
    """Freshness measures when the science appeared, not when we got to it.

    The two coincide for most of this corpus, because ingestion already sets
    stories.published_at from the item. They are still different quantities,
    and they diverge for a minority by up to two days -- which is the whole
    reason to read the item rather than the story.
    """

    rows = published_inputs(conn, limit=40)
    assert rows, "no published stories to check against"

    with conn.cursor() as cur:
        for entry in rows:
            cur.execute(
                """SELECT max(i.published_at) FROM story_items si
                   JOIN items i ON i.id = si.item_id WHERE si.story_id = %s;""",
                (entry.story_id,),
            )
            item_date = cur.fetchone()[0]
            if item_date is not None:
                assert entry.published_at == item_date


def test_the_two_publication_dates_are_not_the_same_column(conn) -> None:
    """If they never diverged the distinction would be untestable, not absent."""

    with conn.cursor() as cur:
        cur.execute(
            """SELECT count(*) FROM stories s, LATERAL (
                 SELECT max(i.published_at) AS item_date
                   FROM story_items si JOIN items i ON i.id = si.item_id
                  WHERE si.story_id = s.id) x
               WHERE s.status = 'published'
                 AND x.item_date IS DISTINCT FROM s.published_at;"""
        )
        assert cur.fetchone()[0] > 0


def test_rungs_are_counted_from_the_current_packet_only(conn) -> None:
    """A story regenerated under a new packet must not inherit old rungs."""

    rows = published_inputs(conn, limit=100)
    with conn.cursor() as cur:
        for entry in rows[:20]:
            cur.execute(
                """SELECT count(*) FROM explanations e
                   JOIN stories s ON s.id = e.story_id
                   WHERE e.story_id = %s AND e.status = 'valid'
                     AND e.evidence_packet_id = s.current_evidence_packet_id;""",
                (entry.story_id,),
            )
            assert cur.fetchone()[0] == entry.rungs


def test_a_story_with_no_verdict_is_read_as_unclear_not_as_missing(conn) -> None:
    """Ranking must not skip a story generated before the judge existed."""

    for entry in published_inputs(conn, limit=200):
        assert entry.significance in {"changes_practice", "incremental", "unclear"}


def test_publication_reuses_an_existing_density_reservation(conn) -> None:
    entry = published_inputs(conn, limit=1)[0]
    identity = density_identity(
        source_name=entry.source_name,
        field=entry.field,
        published_at=entry.published_at,
    )

    with conn.cursor() as cursor:
        position = reserve_density_position(
            cursor,
            story_id=entry.story_id,
            identity=identity,
        )

    assert position == entry.stored_density_position


def test_recomputing_is_idempotent(conn) -> None:
    """The key depends only on things that do not move, so it must not drift.

    This is what lets ranking stop being a scheduled job: running it twice, or a
    year apart, writes the same values.
    """

    assert DATABASE_URL
    first = run_ranking(DATABASE_URL, limit=25)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, effective_at, quality_score FROM stories
               WHERE status = 'published' AND effective_at IS NOT NULL
               ORDER BY id LIMIT 25;"""
        )
        before = cur.fetchall()

    second = run_ranking(DATABASE_URL, limit=25, now=datetime.now(UTC) + timedelta(days=30))
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, effective_at, quality_score FROM stories
               WHERE status = 'published' AND effective_at IS NOT NULL
               ORDER BY id LIMIT 25;"""
        )
        after = cur.fetchall()

    assert first.stories_scored == second.stories_scored
    # A different clock must change nothing: that is the whole property.
    assert before == after


def test_every_published_story_ends_up_with_a_key(conn) -> None:
    assert DATABASE_URL
    run_ranking(DATABASE_URL)

    with conn.cursor() as cur:
        cur.execute(
            """SELECT count(*) FROM stories
               WHERE status = 'published'
                 AND (effective_at IS NULL OR quality_score IS NULL);"""
        )
        assert cur.fetchone()[0] == 0


def test_the_key_is_never_later_than_the_publication_date(conn) -> None:
    """Quality shifts a story earlier. Nothing may shift it into the future."""

    with conn.cursor() as cur:
        cur.execute(
            """SELECT count(*) FROM stories s
               WHERE s.status = 'published' AND s.effective_at > COALESCE(
                 (SELECT max(i.published_at) FROM story_items si
                    JOIN items i ON i.id = si.item_id WHERE si.story_id = s.id),
                 s.created_at) + interval '1 second';"""
        )
        assert cur.fetchone()[0] == 0


def test_stored_quality_stays_inside_the_calibrated_range(conn) -> None:
    """A corpus need not happen to contain every theoretical quality band."""

    with conn.cursor() as cur:
        cur.execute(
            """SELECT min(quality_score), max(quality_score)
               FROM stories WHERE status = 'published';"""
        )
        worst, best = cur.fetchone()

    floor = min(QUALITY_BY_RUNGS.values()) * min(QUALITY_BY_SIGNIFICANCE.values())
    ceiling = max(QUALITY_BY_RUNGS.values()) * max(
        QUALITY_BY_SIGNIFICANCE.values()
    )
    assert floor <= worst <= best <= ceiling
