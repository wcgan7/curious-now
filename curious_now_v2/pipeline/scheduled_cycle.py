from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time
from math import floor
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.core import blobs
from curious_now_v2.core.source_registry import load_source_registry
from curious_now_v2.db.generation import (
    PendingStory,
    list_stories_needing_presentations,
    run_generation,
)
from curious_now_v2.db.hydration import run_hydration
from curious_now_v2.db.publication import run_publication_gate
from curious_now_v2.db.retrieval import run_retrieval
from curious_now_v2.pipeline.run_ingestion import run_ingestion_once

LOCK_NAME = "curious-now-v2-scheduled-cycle"
SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class GenerationBudget:
    daily_usd: float
    accrued_usd: float
    spent_usd: float
    available_usd: float


@dataclass(frozen=True)
class CycleConfig:
    registry_path: Path
    feed_limit: int = 100
    hydration_limit: int = 100
    retrieval_limit: int = 100
    gate_limit: int = 500
    generation_limit: int = 25
    generation_workers: int = 5
    timeout_seconds: float = 30.0
    daily_generation_budget_usd: float = 20.0
    reserved_cost_per_story_usd: float = 0.15
    accessible_fraction: float = 1 / 3


@dataclass(frozen=True)
class CycleResult:
    status: str
    generation_budget: GenerationBudget
    selected_for_generation: int
    counters: dict[str, Any]


def calculate_generation_budget(
    *,
    now: datetime,
    daily_usd: float,
    spent_usd: float,
) -> GenerationBudget:
    """Pace model spend uniformly through the current UTC day."""

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    utc_now = now.astimezone(UTC)
    day_start = datetime.combine(utc_now.date(), time.min, tzinfo=UTC)
    elapsed = max(0.0, min((utc_now - day_start).total_seconds(), SECONDS_PER_DAY))
    accrued = daily_usd * elapsed / SECONDS_PER_DAY
    available = max(0.0, min(daily_usd - spent_usd, accrued - spent_usd))
    return GenerationBudget(
        daily_usd=round(daily_usd, 4),
        accrued_usd=round(accrued, 4),
        spent_usd=round(spent_usd, 4),
        available_usd=round(available, 4),
    )


def generation_spend_today(
    connection: psycopg.Connection[Any], *, now: datetime
) -> float:
    utc_now = now.astimezone(UTC)
    day_start = datetime.combine(utc_now.date(), time.min, tzinfo=UTC)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(SUM((counters->>'cost_usd')::double precision), 0)
            FROM pipeline_runs
            WHERE job_name IN ('generate', 'backfill_titles')
              AND started_at >= %s
              AND started_at < %s + interval '1 day';
            """,
            (day_start, day_start),
        )
        row = cursor.fetchone()
    return float((row or (0.0,))[0] or 0.0)


def _round_robin_sources(stories: list[PendingStory]) -> list[PendingStory]:
    by_source: dict[str, deque[PendingStory]] = defaultdict(deque)
    for story in sorted(stories, key=lambda candidate: candidate.published_at, reverse=True):
        by_source[story.source_name].append(story)
    sources = deque(
        sorted(
            by_source,
            key=lambda name: by_source[name][0].published_at,
            reverse=True,
        )
    )
    ordered: list[PendingStory] = []
    while sources:
        source = sources.popleft()
        ordered.append(by_source[source].popleft())
        if by_source[source]:
            sources.append(source)
    return ordered


def select_generation_batch(
    stories: tuple[PendingStory, ...],
    *,
    limit: int,
    accessible_fraction: float = 1 / 3,
) -> tuple[PendingStory, ...]:
    """Reserve a lane for accessible work while spreading publishers."""

    if limit < 1 or not stories:
        return ()
    accessible = _round_robin_sources(
        [story for story in stories if story.is_accessible_material]
    )
    technical = _round_robin_sources(
        [story for story in stories if not story.is_accessible_material]
    )
    accessible_target = round(limit * accessible_fraction)
    technical_target = limit - accessible_target
    selected = [*technical[:technical_target], *accessible[:accessible_target]]
    remainder = _round_robin_sources(
        [*technical[technical_target:], *accessible[accessible_target:]]
    )
    selected.extend(remainder[: max(0, limit - len(selected))])
    return tuple(selected)


def _start_cycle(connection: psycopg.Connection[Any]) -> UUID:
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO pipeline_runs (job_name, status)
            VALUES ('scheduled_cycle', 'running')
            RETURNING id;
            """
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("pipeline run insert returned no ID")
    return cast(UUID, row[0])


def _finish_cycle(
    connection: psycopg.Connection[Any],
    *,
    run_id: UUID,
    status: str,
    counters: dict[str, Any],
    error: str | None = None,
) -> None:
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE pipeline_runs SET
              status = %s,
              finished_at = now(),
              counters = %s,
              error_summary = %s
            WHERE id = %s;
            """,
            (status, Jsonb(counters), error, run_id),
        )


def run_scheduled_cycle(
    database_url: str,
    *,
    config: CycleConfig,
    dry_run: bool = False,
    now: datetime | None = None,
) -> CycleResult:
    """Run one bounded, non-overlapping ingestion-to-generation cycle."""

    cycle_now = now or datetime.now(UTC)
    with psycopg.connect(database_url, autocommit=True) as lock_connection:
        locked_row = lock_connection.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0));",
            (LOCK_NAME,),
        ).fetchone()
        if not locked_row or not locked_row[0]:
            empty_budget = GenerationBudget(
                daily_usd=config.daily_generation_budget_usd,
                accrued_usd=0,
                spent_usd=0,
                available_usd=0,
            )
            return CycleResult("locked", empty_budget, 0, {})

        try:
            spent = generation_spend_today(lock_connection, now=cycle_now)
            budget = calculate_generation_budget(
                now=cycle_now,
                daily_usd=config.daily_generation_budget_usd,
                spent_usd=spent,
            )
            with psycopg.connect(database_url, autocommit=True) as queue_connection:
                pending = list_stories_needing_presentations(
                    queue_connection,
                    limit=10_000,
                )
            budget_limit = floor(
                budget.available_usd / config.reserved_cost_per_story_usd
            )
            selected = select_generation_batch(
                pending,
                limit=min(config.generation_limit, budget_limit),
                accessible_fraction=config.accessible_fraction,
            )
            if dry_run:
                return CycleResult(
                    status="dry_run",
                    generation_budget=budget,
                    selected_for_generation=len(selected),
                    counters={"generation_queue": len(pending)},
                )

            run_id = _start_cycle(lock_connection)
            counters: dict[str, Any] = {}
            try:
                registry = load_source_registry(config.registry_path)
                print("cycle: ingesting due feeds", flush=True)  # noqa: T201
                ingestion = run_ingestion_once(
                    database_url=database_url,
                    registry=registry,
                    limit=config.feed_limit,
                    timeout_seconds=config.timeout_seconds,
                )
                counters["ingestion"] = {
                    key: value
                    for key, value in asdict(ingestion).items()
                    if key != "run_id"
                }
                print(  # noqa: T201
                    "cycle: ingestion complete "
                    f"({ingestion.feeds_succeeded}/{ingestion.feeds_attempted} feeds, "
                    f"{ingestion.items_inserted} new items)",
                    flush=True,
                )
                writable, detail = blobs.usable()
                if not writable:
                    raise RuntimeError(f"blob store unusable: {detail}")
                print("cycle: retrieving article text", flush=True)  # noqa: T201
                retrieval = run_retrieval(
                    database_url,
                    limit=config.retrieval_limit,
                    timeout_seconds=config.timeout_seconds,
                )
                counters["retrieval"] = asdict(retrieval)
                print(  # noqa: T201
                    f"cycle: retrieval complete ({retrieval.retrieved}/"
                    f"{retrieval.attempted} retrieved)",
                    flush=True,
                )
                print("cycle: hydrating paper metadata", flush=True)  # noqa: T201
                hydration = run_hydration(
                    database_url,
                    limit=config.hydration_limit,
                    timeout_seconds=config.timeout_seconds,
                )
                counters["hydration"] = asdict(hydration)
                print(  # noqa: T201
                    f"cycle: hydration complete ({hydration.papers_hydrated}/"
                    f"{hydration.papers_attempted} hydrated)",
                    flush=True,
                )
                print("cycle: gating changed evidence", flush=True)  # noqa: T201
                gate = run_publication_gate(
                    database_url,
                    limit=config.gate_limit,
                    changed_only=True,
                )
                counters["gate"] = asdict(gate)
                print(  # noqa: T201
                    f"cycle: gate complete ({gate.evaluated} evaluated)",
                    flush=True,
                )

                # Refresh after retrieval and gating: the preflight selection
                # intentionally did not include stories made ready in this run.
                with psycopg.connect(database_url, autocommit=True) as queue_connection:
                    pending = list_stories_needing_presentations(
                        queue_connection,
                        limit=10_000,
                    )
                spent = generation_spend_today(lock_connection, now=datetime.now(UTC))
                budget = calculate_generation_budget(
                    now=datetime.now(UTC),
                    daily_usd=config.daily_generation_budget_usd,
                    spent_usd=spent,
                )
                budget_limit = floor(
                    budget.available_usd / config.reserved_cost_per_story_usd
                )
                selected = select_generation_batch(
                    pending,
                    limit=min(config.generation_limit, budget_limit),
                    accessible_fraction=config.accessible_fraction,
                )
                if selected:
                    print(  # noqa: T201
                        f"cycle: generating {len(selected)} stories "
                        f"(${budget.available_usd:.2f} accrued budget available)",
                        flush=True,
                    )
                    generation = run_generation(
                        database_url,
                        limit=len(selected),
                        story_ids=[story.story_id for story in selected],
                        workers=min(config.generation_workers, len(selected)),
                    )
                    counters["generation"] = asdict(generation)
                else:
                    print("cycle: no generation budget or backlog", flush=True)  # noqa: T201
                    counters["generation"] = {"attempted": 0, "cost_usd": 0.0}
                counters["generation_budget"] = asdict(budget)
                _finish_cycle(
                    lock_connection,
                    run_id=run_id,
                    status="succeeded",
                    counters=counters,
                )
                return CycleResult(
                    "succeeded", budget, len(selected), counters
                )
            except Exception as exc:
                _finish_cycle(
                    lock_connection,
                    run_id=run_id,
                    status="failed",
                    counters=counters,
                    error=f"{type(exc).__name__}: {exc}"[:2000],
                )
                raise
        finally:
            lock_connection.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0));",
                (LOCK_NAME,),
            )
