from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.core.enums import (
    AccessClass,
    ContentType,
    SourceRole,
    StoryItemRole,
)
from curious_now_v2.core.models import SourceItem, StoryDraft
from curious_now_v2.pipeline.ranking import rank_stories


@dataclass(frozen=True)
class RankingRunResult:
    stories_scored: int
    top_score: float


def load_story_drafts(
    connection: psycopg.Connection[Any],
    *,
    limit: int | None = None,
) -> tuple[StoryDraft, ...]:
    """Load published stories with their source items for scoring."""

    query = """
        SELECT
          s.id,
          s.working_title,
          s.current_evidence_packet_id,
          i.id,
          i.source_id,
          src.name,
          src.role,
          si.role,
          i.title,
          i.url,
          i.content_type,
          i.access_class,
          i.published_at,
          ip.paper_id
        FROM stories s
        JOIN story_items si ON si.story_id = s.id
        JOIN items i ON i.id = si.item_id
        JOIN sources src ON src.id = i.source_id
        LEFT JOIN item_papers ip ON ip.item_id = i.id
        WHERE s.status = 'published'
        ORDER BY s.published_at DESC NULLS LAST, s.id, i.published_at DESC
    """
    parameters: tuple[object, ...] = ()
    if limit is not None:
        query = f"""
            WITH ranked AS (
              SELECT id FROM stories
              WHERE status = 'published'
              ORDER BY published_at DESC NULLS LAST, id
              LIMIT %s
            )
            {query.replace("WHERE s.status = 'published'", "WHERE s.id IN (SELECT id FROM ranked)")}
        """
        parameters = (limit,)

    grouped: dict[UUID, list[SourceItem]] = {}
    titles: dict[UUID, str] = {}
    packets: dict[UUID, UUID | None] = {}
    with connection.cursor() as cursor:
        cursor.execute(query, parameters)
        for row in cursor:
            (
                story_id,
                working_title,
                packet_id,
                item_id,
                source_id,
                source_name,
                source_role,
                story_role,
                title,
                url,
                content_type,
                access_class,
                published_at,
                paper_id,
            ) = row
            titles[story_id] = working_title
            packets[story_id] = packet_id
            grouped.setdefault(story_id, []).append(
                SourceItem(
                    item_id=item_id,
                    source_id=source_id,
                    source_name=source_name,
                    source_role=SourceRole(source_role),
                    role=StoryItemRole(story_role),
                    title=title,
                    url=url,
                    content_type=ContentType(content_type),
                    access_class=AccessClass(access_class),
                    published_at=published_at,
                    paper_id=paper_id,
                )
            )

    return tuple(
        StoryDraft(
            story_id=story_id,
            working_title=titles[story_id],
            items=tuple(items),
            current_evidence_packet_id=packets[story_id],
        )
        for story_id, items in grouped.items()
        if items
    )


def run_ranking(
    database_url: str,
    *,
    limit: int | None = None,
    now: datetime | None = None,
) -> RankingRunResult:
    """Score every published story and persist inspectable reasons.

    Ranking is idempotent: rerunning with the same data and clock produces the
    same scores.
    """

    moment = now or datetime.now(UTC)
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
            stories = load_story_drafts(connection, limit=limit)
            ranked = rank_stories(stories, now=moment)
            with connection.transaction(), connection.cursor() as cursor:
                cursor.executemany(
                    """
                    UPDATE stories SET
                      feed_score = %s,
                      ranking_reasons = %s,
                      ranked_at = %s,
                      updated_at = now()
                    WHERE id = %s;
                    """,
                    [
                        (
                            entry.score,
                            Jsonb(
                                {
                                    "base_score": round(entry.base_score, 6),
                                    "variety_factor": round(entry.variety_factor, 6),
                                    "principal_source": entry.principal_source,
                                    "reasons": list(entry.reasons),
                                }
                            ),
                            moment,
                            entry.story_id,
                        )
                        for entry in ranked
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
                (Jsonb({"stories_scored": len(ranked)}), run_id),
            )

    return RankingRunResult(
        stories_scored=len(ranked),
        top_score=ranked[0].score if ranked else 0.0,
    )
