"""Recomputing the feed's sort key.

The key is written once, when a story is published, and does not go stale: it
is time-invariant by construction, so there is nothing here for a scheduler to
run. What remains is a recompute for changes to the quality tables, half-life
or source-density calibration. Stored density positions survive that
recompute; new stories append to their source/category/day cohort.

That is a deliberate operator action rather than a cron. The previous
arrangement was the opposite: a periodic pass nothing invoked, leaving 113 of
168 published stories at zero, and which could not have stayed correct anyway
because 35% of the score decayed on an 18-hour half-life.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.core.fields import group_of
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
    eligible_depths: int
    significance: str
    #: Which feed the story came down. Not a term in the score -- only what
    #: decides whose turn it is when several stories share a key.
    source_name: str
    #: When we first saw it, which is the closest thing we hold to arrival
    #: order and is what orders a source's queue.
    first_seen: datetime
    field: str | None = None
    stored_density_key: tuple[str, str, str] | None = None
    stored_density_position: int | None = None


@dataclass(frozen=True)
class DensityIdentity:
    source: str
    category: str
    day: str

    @property
    def key(self) -> tuple[str, str, str]:
        return self.source, self.category, self.day

    @property
    def lock_key(self) -> str:
        return json.dumps(self.key, separators=(",", ":"))


def density_identity(
    *, source_name: str, field: str | None, published_at: datetime
) -> DensityIdentity:
    """The stable cohort within which repeated-source positions are assigned."""

    return DensityIdentity(
        source=source_name,
        category=group_of(field) or "unfiled",
        day=published_at.date().isoformat(),
    )


def _stored_density(value: object) -> tuple[tuple[str, str, str] | None, int | None]:
    if not isinstance(value, dict):
        return None, None
    density = value.get("density")
    if not isinstance(density, dict):
        return None, None
    source = density.get("source")
    category = density.get("category")
    day = density.get("day")
    position = density.get("position")
    if not all(isinstance(part, str) for part in (source, category, day)):
        return None, None
    if not isinstance(position, int) or isinstance(position, bool) or position < 0:
        return None, None
    return (str(source), str(category), str(day)), position


def ranking_payload(
    score: scoring.StoryScore,
    *,
    identity: DensityIdentity,
    density_position: int,
) -> dict[str, object]:
    """The operator-readable facts behind one stored ranking key."""

    return {
        "quality": round(score.quality, 6),
        "offset_hours": round(score.offset_hours, 2),
        "reasons": list(score.reasons),
        "density": {
            "source": identity.source,
            "category": identity.category,
            "day": identity.day,
            "position": density_position,
            "factor": round(score.density_factor, 6),
            "offset_hours": round(score.density_offset_hours, 2),
        },
    }


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
              cardinality(s.supported_depths) AS eligible_depths,
              COALESCE(s.significance, 'unclear'),
              COALESCE(d.source_name, ''),
              s.created_at,
              s.field,
              s.ranking_reasons
            FROM stories s
            LEFT JOIN dated d ON d.story_id = s.id
            WHERE s.status = 'published'
            ORDER BY s.id
            {"LIMIT %s" if limit else ""};
            """,
            (limit,) if limit else (),
        )
        inputs: list[RankingInput] = []
        for row in cursor.fetchall():
            stored_key, stored_position = _stored_density(row[8])
            inputs.append(
                RankingInput(
                    story_id=row[0],
                    published_at=row[1],
                    rungs=int(row[2]),
                    eligible_depths=int(row[3]),
                    significance=str(row[4]),
                    source_name=str(row[5]),
                    first_seen=row[6],
                    field=row[7],
                    stored_density_key=stored_key,
                    stored_density_position=stored_position,
                )
            )
        return inputs


def density_positions(inputs: list[RankingInput]) -> dict[UUID, int]:
    """Assign append-stable positions within source/category/publication-day.

    Positions already written for the same cohort are authoritative. New or
    moved stories join the back in first-seen order, so adding an item never
    changes an earlier item's key. A duplicate stored position is repaired by
    keeping the earliest arrival in place and appending the other.
    """

    groups: dict[tuple[str, str, str], list[RankingInput]] = {}
    for entry in inputs:
        identity = density_identity(
            source_name=entry.source_name,
            field=entry.field,
            published_at=entry.published_at,
        )
        groups.setdefault(identity.key, []).append(entry)

    positions: dict[UUID, int] = {}
    for key, entries in groups.items():
        ordered = sorted(
            entries, key=lambda value: (value.first_seen, str(value.story_id))
        )
        stored = [
            (index, entry.stored_density_position)
            for index, entry in enumerate(ordered)
            if entry.stored_density_key == key
            and entry.stored_density_position is not None
        ]
        # During the first corpus backfill a limited run may write only some
        # members of a previously unpositioned cohort. If every stored value
        # agrees with the deterministic first-seen ordering, reconstruct the
        # rest in that same ordering. This makes partial runs idempotent. Once
        # an append-only reservation differs from that historical ordering, the
        # preservation path below takes over and no established key can move.
        if len({position for _, position in stored}) == len(stored) and all(
            index == position for index, position in stored
        ):
            positions.update(
                {entry.story_id: index for index, entry in enumerate(ordered)}
            )
            continue

        used: set[int] = set()
        unassigned: list[RankingInput] = []
        for entry in ordered:
            position = entry.stored_density_position
            if (
                entry.stored_density_key == key
                and position is not None
                and position not in used
            ):
                positions[entry.story_id] = position
                used.add(position)
            else:
                unassigned.append(entry)

        next_position = max(used, default=-1) + 1
        for entry in unassigned:
            positions[entry.story_id] = next_position
            used.add(next_position)
            next_position += 1
    return positions


def queue_positions(
    inputs: list[RankingInput],
    *,
    density: dict[UUID, int] | None = None,
) -> dict[UUID, int]:
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
            rungs_earned=scoring.completion_rungs(
                valid_depths=entry.rungs,
                eligible_depths=entry.eligible_depths,
            ),
            significance=entry.significance,
            density_position=(density or {}).get(entry.story_id, 0),
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


def reserve_density_position(
    cursor: psycopg.Cursor[Any],
    *,
    story_id: UUID,
    identity: DensityIdentity,
) -> int:
    """Reserve the next append-only position while publishing one story.

    Generation can publish several stories concurrently. A transaction-scoped
    advisory lock serialises only writers to the same source/category/day; all
    unrelated stories remain independent. Regenerating a story in the same
    cohort reuses its position instead of moving it to the back.
    """

    cursor.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0));",
        (identity.lock_key,),
    )
    cursor.execute("SELECT ranking_reasons FROM stories WHERE id = %s;", (story_id,))
    row = cursor.fetchone()
    if row is not None:
        stored_key, stored_position = _stored_density(row[0])
        if stored_key == identity.key and stored_position is not None:
            return stored_position

    cursor.execute(
        """
        SELECT COALESCE(
          max(
            CASE
              WHEN jsonb_typeof(ranking_reasons->'density'->'position') = 'number'
              THEN (ranking_reasons->'density'->>'position')::integer
            END
          ),
          -1
        ) + 1
        FROM stories
        WHERE status = 'published'
          AND id <> %s
          AND ranking_reasons->'density'->>'source' = %s
          AND ranking_reasons->'density'->>'category' = %s
          AND ranking_reasons->'density'->>'day' = %s;
        """,
        (
            story_id,
            identity.source,
            identity.category,
            identity.day,
        ),
    )
    position_row = cursor.fetchone()
    if position_row is None:
        raise RuntimeError("density position query returned no row")
    return int(position_row[0])


def run_ranking(
    database_url: str,
    *,
    limit: int | None = None,
    now: datetime | None = None,
) -> RankingRunResult:
    """Recompute every published story's sort key from what it earned.

    Idempotent by construction: quality facts do not move, and stored density
    positions are retained while new stories append. Running this twice, or a
    year apart, therefore writes the same values.
    """

    moment = now or datetime.now(UTC)
    scored: list[tuple[RankingInput, scoring.StoryScore, int]] = []

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
            # Positions need the whole cohort even when an operator limits the
            # number of rows rewritten. Computing a position from an arbitrary
            # ID-limited subset would make `--limit` silently change the key.
            all_inputs = published_inputs(connection)
            density = density_positions(all_inputs)
            positions = queue_positions(all_inputs, density=density)
            inputs = all_inputs[:limit] if limit is not None else all_inputs
            scored = [
                (
                    entry,
                    scoring.score_story(
                        published_at=entry.published_at,
                        rungs_earned=scoring.completion_rungs(
                            valid_depths=entry.rungs,
                            eligible_depths=entry.eligible_depths,
                        ),
                        significance=entry.significance,
                        queue_position=positions.get(entry.story_id, 0),
                        density_position=density.get(entry.story_id, 0),
                    ),
                    density.get(entry.story_id, 0),
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
                                score.quality,
                                score.effective_at,
                                Jsonb(
                                    ranking_payload(
                                        score,
                                        identity=density_identity(
                                            source_name=entry.source_name,
                                            field=entry.field,
                                            published_at=entry.published_at,
                                        ),
                                        density_position=density_position,
                                    )
                                ),
                                moment,
                                entry.story_id,
                            )
                            for entry, score, density_position in scored
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
            (score.effective_at for _, score, _ in scored), default=None
        ),
    )
