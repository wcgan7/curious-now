from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.core.enums import ContentType, SourceRole
from curious_now_v2.pipeline.story_gate import ItemText, StoryGate, gate_story

PRIMARY_TYPES = frozenset(
    {
        ContentType.PREPRINT.value,
        ContentType.PEER_REVIEWED.value,
        ContentType.REPORT.value,
        ContentType.DATASET.value,
    }
)


@dataclass(frozen=True)
class GateRunResult:
    evaluated: int
    # Eligible, not published. The gate decides what the text can support;
    # whether a reader is offered it depends on a presentation existing, which
    # is generation's call. Calling this `published` described what the gate
    # used to do, which is how a feed of 295 stories came to hold 8 explanations.
    eligible: int
    ineligible: int
    by_depth: dict[str, int]


def _load_story_items(
    connection: psycopg.Connection[Any],
    *,
    limit: int | None,
) -> dict[UUID, list[ItemText]]:
    """Every story's retrieved text, keyed by story."""

    query = """
        SELECT
          s.id,
          src.name,
          COALESCE(i.full_text, ''),
          i.text_structure,
          i.content_type,
          src.role,
          COALESCE(i.full_text_words, 0)
        FROM stories s
        JOIN story_items si ON si.story_id = s.id
        JOIN items i ON i.id = si.item_id
        JOIN sources src ON src.id = i.source_id
        WHERE s.status <> 'hidden'
          AND s.withheld_kind IS NULL
    """
    parameters: tuple[object, ...] = ()
    if limit is not None:
        query += """
          AND s.id IN (
            SELECT id FROM stories
            WHERE status <> 'hidden' AND withheld_kind IS NULL
            ORDER BY gated_at NULLS FIRST, last_evidence_at DESC
            LIMIT %s
          )
        """
        parameters = (limit,)

    grouped: dict[UUID, list[ItemText]] = {}
    with connection.cursor() as cursor:
        cursor.execute(query, parameters)
        for (
            story_id,
            source_name,
            text,
            structure,
            content_type,
            source_role,
            words,
        ) in cursor:
            sections = (structure or {}).get("sections") or []
            grouped.setdefault(story_id, []).append(
                ItemText(
                    source_name=source_name,
                    text=text,
                    has_structure=any(
                        section.get("kind") not in (None, "other")
                        for section in sections
                    ),
                    is_primary_material=(
                        content_type in PRIMARY_TYPES
                        or source_role == SourceRole.PRIMARY_RESEARCH.value
                    ),
                    words=words,
                )
            )
    return grouped


def _store_gate(
    connection: psycopg.Connection[Any],
    *,
    story_id: UUID,
    gate: StoryGate,
    now: datetime,
) -> None:
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE stories SET
              -- Eligibility is not publication. A story goes out when a
              -- validated presentation exists for it, which is decided in
              -- generation; the gate must not promote one on word count, and
              -- must not demote one that already has an explanation.
              status = CASE
                WHEN status IN ('hidden', 'published') THEN status
                ELSE 'draft'
              END,
              supported_depths = %s,
              publication_reasons = %s,
              gated_at = %s,
              -- published_at is not set here either: it marks when a reader
              -- could first open the story, which is when generation published
              -- it, not when the gate found the text long enough.
              updated_at = now()
            WHERE id = %s;
            """,
            (
                [depth.value for depth in gate.supported_depths],
                Jsonb(list(gate.reasons[:10])),
                now,
                story_id,
            ),
        )


def run_publication_gate(
    database_url: str,
    *,
    limit: int | None = None,
) -> GateRunResult:
    """Decide which stories have evidence worth opening.

    Withheld stories keep every item: an unfetchable paywalled paper is still
    the primary source for the journalism that covers it, and discarding it
    would strip the peer-review status from a story that does publish.
    """

    now = datetime.now(UTC)
    eligible = 0
    by_depth: dict[str, int] = {}

    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_runs (job_name, status)
                VALUES ('publication_gate', 'running')
                RETURNING id;
                """
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("pipeline run insert returned no ID")
            run_id = cast(UUID, row[0])

        stories = _load_story_items(connection, limit=limit)
        for story_id, items in stories.items():
            gate = gate_story(tuple(items))
            _store_gate(connection, story_id=story_id, gate=gate, now=now)
            if gate.publishable:
                eligible += 1
                for depth in gate.supported_depths:
                    by_depth[depth.value] = by_depth.get(depth.value, 0) + 1

        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_runs SET
                  status = 'succeeded',
                  finished_at = now(),
                  counters = %s
                WHERE id = %s;
                """,
                (
                    Jsonb(
                        {
                            "evaluated": len(stories),
                            "eligible": eligible,
                            "ineligible": len(stories) - eligible,
                            **by_depth,
                        }
                    ),
                    run_id,
                ),
            )

    return GateRunResult(
        evaluated=len(stories),
        eligible=eligible,
        ineligible=len(stories) - eligible,
        by_depth=by_depth,
    )
