#!/usr/bin/env python3
"""Backfill reader-facing titles from the current stored Idea.

News and magazine headlines are deliberately absent from this queue. Technical
works use the same direct title function as new generation, so backfill and
future stories cannot drift onto different prompts.
"""

from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from math import floor
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.generation.client import CodexGenerator
from curious_now_v2.generation.direct import (
    PRIMARY_TYPES,
    TITLE_PROMPT_VERSION,
    DirectTitle,
    generate_title,
)
from curious_now_v2.pipeline.scheduled_cycle import (
    LOCK_NAME,
    calculate_generation_budget,
    generation_spend_today,
)


@dataclass(frozen=True)
class PendingTitle:
    story_id: UUID
    evidence_packet_id: UUID
    source_title: str
    idea: str


def pending_titles(
    connection: psycopg.Connection[Any], *, limit: int
) -> tuple[PendingTitle, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT s.id, ep.id, item.title, idea.plain_text
            FROM stories s
            JOIN evidence_packets ep ON ep.id = s.current_evidence_packet_id
            JOIN items item
              ON item.id = NULLIF(ep.provenance->>'grounding_item', '')::uuid
            JOIN explanations idea
              ON idea.story_id = s.id
             AND idea.evidence_packet_id = ep.id
             AND idea.depth = 'glance'
             AND idea.status = 'valid'
            WHERE s.status = 'published'
              AND item.content_type = ANY(%s)
              AND NOT EXISTS (
                SELECT 1 FROM display_titles title
                WHERE title.story_id = s.id
                  AND title.prompt_version = %s
                  AND title.status = 'valid'
              )
            ORDER BY COALESCE(s.published_at, s.created_at) DESC, s.id
            LIMIT %s;
            """,
            (list(PRIMARY_TYPES), TITLE_PROMPT_VERSION, limit),
        )
        return tuple(
            PendingTitle(
                story_id=row[0],
                evidence_packet_id=row[1],
                source_title=row[2],
                idea=row[3],
            )
            for row in cursor
        )


def store_title(
    database_url: str,
    *,
    pending: PendingTitle,
    title: DirectTitle,
    model: str,
) -> bool:
    if not title.valid:
        return False
    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM conceptual_spines
                WHERE story_id = %s AND evidence_packet_id = %s
                ORDER BY version DESC
                LIMIT 1;
                """,
                (pending.story_id, pending.evidence_packet_id),
            )
            row = cursor.fetchone()
            spine_id = row[0] if row else None
            cursor.execute(
                """
                SELECT COALESCE(max(version), 0) + 1
                FROM display_titles WHERE story_id = %s;
                """,
                (pending.story_id,),
            )
            version_row = cursor.fetchone()
            if version_row is None:
                raise RuntimeError("title version query returned no row")
            cursor.execute(
                """
                INSERT INTO display_titles (
                  story_id, evidence_packet_id, conceptual_spine_id, version,
                  text, status, prompt_version, model_provider, model_name,
                  validated_at
                )
                VALUES (%s, %s, %s, %s, %s, 'valid', %s, 'openai', %s, now())
                RETURNING id;
                """,
                (
                    pending.story_id,
                    pending.evidence_packet_id,
                    spine_id,
                    version_row[0],
                    title.text,
                    title.prompt_version,
                    model,
                ),
            )
            title_row = cursor.fetchone()
            if title_row is None:
                raise RuntimeError("display title insert returned no ID")
            cursor.execute(
                """
                UPDATE stories SET current_display_title_id = %s, updated_at = now()
                WHERE id = %s AND current_evidence_packet_id = %s;
                """,
                (title_row[0], pending.story_id, pending.evidence_packet_id),
            )
            return cursor.rowcount == 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url", default=os.environ.get("CURIOUS_NOW_V2_DATABASE_URL")
    )
    parser.add_argument("--limit", type=int, default=10_000)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--daily-budget-usd", type=float, default=20.0)
    parser.add_argument("--reserved-cost-usd", type=float, default=0.01)
    parser.add_argument(
        "--use-daily-headroom",
        action="store_true",
        help=(
            "use unspent capacity up to the UTC-day cap instead of only the "
            "amount accrued so far; intended for a one-time maintenance run"
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.database_url:
        raise SystemExit("set CURIOUS_NOW_V2_DATABASE_URL or pass --database-url")
    if min(
        args.limit,
        args.workers,
        args.daily_budget_usd,
        args.reserved_cost_usd,
    ) <= 0:
        raise SystemExit("limit, workers, budget, and reservation must be positive")

    now = datetime.now(UTC)
    with psycopg.connect(args.database_url, autocommit=True) as lock_connection:
        locked = lock_connection.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0));",
            (LOCK_NAME,),
        ).fetchone()
        if not locked or not locked[0]:
            raise SystemExit("scheduled pipeline is running; retry after it finishes")
        try:
            spent = generation_spend_today(lock_connection, now=now)
            budget = calculate_generation_budget(
                now=now,
                daily_usd=args.daily_budget_usd,
                spent_usd=spent,
            )
            available = (
                max(args.daily_budget_usd - spent, 0.0)
                if args.use_daily_headroom
                else budget.available_usd
            )
            limit = min(
                args.limit,
                floor(available / args.reserved_cost_usd),
            )
            if limit < 1:
                print(  # noqa: T201
                    f"no title budget (${available:.2f} available)"
                )
                return
            print(  # noqa: T201
                f"title budget: ${available:.2f} available, "
                f"reserving ${args.reserved_cost_usd:.2f} each"
            )
            targets = pending_titles(lock_connection, limit=limit)
            if not targets:
                print("no technical stories need titles")  # noqa: T201
                return

            with lock_connection.transaction(), lock_connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO pipeline_runs (job_name, status)
                    VALUES ('backfill_titles', 'running') RETURNING id;
                    """
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("pipeline run insert returned no ID")
                run_id = cast(UUID, row[0])

            generator = CodexGenerator(model="gpt-5.6-luna", effort="low")

            def generate(pending: PendingTitle) -> tuple[PendingTitle, DirectTitle]:
                return pending, generate_title(
                    generator,
                    source_title=pending.source_title,
                    idea=pending.idea,
                )

            written = 0
            failed = 0
            cost = 0.0
            errors: list[str] = []
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(generate, target) for target in targets]
                for index, future in enumerate(as_completed(futures), start=1):
                    try:
                        pending, title = future.result()
                        cost += title.completion.usage.cost(generator.model)
                        if store_title(
                            args.database_url,
                            pending=pending,
                            title=title,
                            model=generator.model,
                        ):
                            written += 1
                        else:
                            failed += 1
                            errors.append(
                                f"{pending.story_id}: "
                                f"{title.completion.error or 'empty title'}"
                            )
                    except Exception as exc:  # noqa: BLE001
                        failed += 1
                        errors.append(f"{type(exc).__name__}: {exc}")
                    if index % 25 == 0 or index == len(targets):
                        print(  # noqa: T201
                            f"  {index}/{len(targets)} titles="
                            f"{written} failed={failed} ${cost:.2f}",
                            flush=True,
                        )

            counters = {
                "attempted": len(targets),
                "titles_generated": written,
                "failed": failed,
                "cost_usd": round(cost, 4),
                "prompt_version": TITLE_PROMPT_VERSION,
            }
            with lock_connection.transaction(), lock_connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE pipeline_runs SET
                      status = %s, finished_at = now(), counters = %s,
                      error_summary = %s
                    WHERE id = %s;
                    """,
                    (
                        "succeeded" if not failed else "partial",
                        Jsonb(counters),
                        "\n".join(errors[:10]) or None,
                        run_id,
                    ),
                )
            print(  # noqa: T201
                f"completed title backfill: {written}/{len(targets)}, ${cost:.2f}"
            )
        finally:
            lock_connection.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0));",
                (LOCK_NAME,),
            )


if __name__ == "__main__":
    main()
