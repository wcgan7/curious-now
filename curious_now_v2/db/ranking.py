"""Recomputing the feed's sort key.

The key is written once, when a story is published, and does not go stale: it
is time-invariant by construction, so there is nothing here for a scheduler to
run. What remains is a recompute, for the one thing that invalidates every key
at once -- a change to the quality tables or to the half-life.

That is a deliberate operator action rather than a cron. The previous
arrangement was the opposite: a periodic pass nothing invoked, leaving 113 of
168 published stories at zero, and which could not have stayed correct anyway
because 35% of the score decayed on an 18-hour half-life.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.pipeline import scoring


@dataclass(frozen=True)
class RankingRunResult:
    stories_scored: int
    newest_effective_at: datetime | None


@dataclass(frozen=True)
class RankingInput:
    story_id: UUID
    published_at: datetime
    rungs: int
    significance: str
    #: Which feed the story came down. Not a term in the score -- only what
    #: decides whose turn it is when several stories share a key.
    source_name: str
    #: When we first saw it, which is the closest thing we hold to arrival
    #: order and is what orders a source's queue.
    first_seen: datetime


def published_inputs(
    connection: psycopg.Connection[Any], *, limit: int | None = None
) -> list[RankingInput]:
    """What every published story earned, and when its science appeared.

    The publication date is the item's, not the story's: freshness measures how
    recent the work is, where `stories.published_at` records when we got round
    to showing it.

    The source is the one that supplied that date. A story can carry several --
    a paper and the journalism about it -- and taking the source of the item
    whose date set the key is the only choice that is not arbitrary.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH dated AS (
              SELECT DISTINCT ON (si.story_id)
                si.story_id,
                i.published_at,
                src.name AS source_name
              FROM story_items si
              JOIN items i ON i.id = si.item_id
              JOIN sources src ON src.id = i.source_id
              WHERE i.published_at IS NOT NULL
              ORDER BY si.story_id, i.published_at DESC, src.name
            )
            SELECT
              s.id,
              COALESCE(d.published_at, s.created_at) AS published,
              (SELECT count(*) FROM explanations e
                WHERE e.story_id = s.id
                  AND e.evidence_packet_id = s.current_evidence_packet_id
                  AND e.status = 'valid') AS rungs,
              COALESCE(s.significance, 'unclear'),
              COALESCE(d.source_name, ''),
              s.created_at
            FROM stories s
            LEFT JOIN dated d ON d.story_id = s.id
            WHERE s.status = 'published'
            ORDER BY s.id
            {"LIMIT %s" if limit else ""};
            """,
            (limit,) if limit else (),
        )
        return [
            RankingInput(
                story_id=row[0],
                published_at=row[1],
                rungs=int(row[2]),
                significance=str(row[3]),
                source_name=str(row[4]),
                first_seen=row[5],
            )
            for row in cursor.fetchall()
        ]


def queue_positions(inputs: list[RankingInput]) -> dict[UUID, int]:
    """Whose turn it is, among stories from one source sharing one key.

    The key a story would have on quality alone is what decides which stories
    are competing: they are the ones a reader would otherwise see in UUID
    order. Within each (key, source) the queue runs oldest-first by when we
    first saw the story, so a story's position never changes once assigned --
    anything arriving later joins the back.
    """

    order: dict[tuple[datetime, str], list[RankingInput]] = {}
    for entry in inputs:
        base = scoring.score_story(
            published_at=entry.published_at,
            rungs_earned=entry.rungs,
            significance=entry.significance,
        )
        # Rounded to the second, because the quality offsets are whole hours
        # and floating point should not be what decides whether two stories are
        # in the same queue.
        key = base.effective_at.replace(microsecond=0)
        order.setdefault((key, entry.source_name), []).append(entry)

    positions: dict[UUID, int] = {}
    for competing in order.values():
        competing.sort(key=lambda entry: (entry.first_seen, str(entry.story_id)))
        for index, entry in enumerate(competing):
            positions[entry.story_id] = index
    return positions


def run_ranking(
    database_url: str,
    *,
    limit: int | None = None,
    now: datetime | None = None,
) -> RankingRunResult:
    """Recompute every published story's sort key from what it earned.

    Idempotent by construction: the key depends only on the story's publication
    date, its rungs and its significance, none of which move. Running this twice
    writes the same values, and running it a year later writes them again.
    """

    moment = now or datetime.now(UTC)
    scored: list[tuple[UUID, scoring.StoryScore]] = []

    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_runs (job_name, status)
                VALUES ('rank', 'running')
                RETURNING id;
                """
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("pipeline run insert returned no ID")
            run_id = cast(UUID, row[0])

        try:
            inputs = published_inputs(connection, limit=limit)
            positions = queue_positions(inputs)
            scored = [
                (
                    entry.story_id,
                    scoring.score_story(
                        published_at=entry.published_at,
                        rungs_earned=entry.rungs,
                        significance=entry.significance,
                        queue_position=positions.get(entry.story_id, 0),
                    ),
                )
                for entry in inputs
            ]
            if scored:
                with connection.transaction(), connection.cursor() as cursor:
                    cursor.executemany(
                        """
                        UPDATE stories SET
                          quality_score = %s,
                          effective_at = %s,
                          ranking_reasons = %s,
                          ranked_at = %s,
                          updated_at = now()
                        WHERE id = %s;
                        """,
                        [
                            (
                                entry.quality,
                                entry.effective_at,
                                Jsonb(
                                    {
                                        "quality": round(entry.quality, 6),
                                        "offset_hours": round(entry.offset_hours, 2),
                                        "reasons": list(entry.reasons),
                                    }
                                ),
                                moment,
                                story_id,
                            )
                            for story_id, entry in scored
                        ],
                    )
        except Exception as exc:
            with connection.transaction(), connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE pipeline_runs SET
                      status = 'failed',
                      finished_at = now(),
                      error_summary = %s
                    WHERE id = %s;
                    """,
                    (f"{type(exc).__name__}: {exc}", run_id),
                )
            raise

        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_runs SET
                  status = 'succeeded',
                  finished_at = now(),
                  counters = %s
                WHERE id = %s;
                """,
                (Jsonb({"stories_scored": len(scored)}), run_id),
            )

    return RankingRunResult(
        stories_scored=len(scored),
        newest_effective_at=max(
            (entry.effective_at for _, entry in scored), default=None
        ),
    )
