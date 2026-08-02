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


def published_inputs(
    connection: psycopg.Connection[Any], *, limit: int | None = None
) -> list[tuple[UUID, datetime, int, str]]:
    """What every published story earned, and when its science appeared.

    The publication date is the item's, not the story's: freshness measures how
    recent the work is, where `stories.published_at` records when we got round
    to showing it.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
              s.id,
              COALESCE(
                (SELECT max(i.published_at) FROM story_items si
                   JOIN items i ON i.id = si.item_id
                  WHERE si.story_id = s.id),
                s.created_at
              ) AS published,
              (SELECT count(*) FROM explanations e
                WHERE e.story_id = s.id
                  AND e.evidence_packet_id = s.current_evidence_packet_id
                  AND e.status = 'valid') AS rungs,
              COALESCE(s.significance, 'unclear')
            FROM stories s
            WHERE s.status = 'published'
            ORDER BY s.id
            {"LIMIT %s" if limit else ""};
            """,
            (limit,) if limit else (),
        )
        return [(row[0], row[1], int(row[2]), str(row[3])) for row in cursor.fetchall()]


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
            scored = [
                (
                    story_id,
                    scoring.score_story(
                        published_at=published,
                        rungs_earned=rungs,
                        significance=verdict,
                    ),
                )
                for story_id, published, rungs, verdict in published_inputs(
                    connection, limit=limit
                )
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
