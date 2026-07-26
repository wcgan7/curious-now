from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import httpx
import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.core.source_registry import SourceRegistry
from curious_now_v2.db.ingestion import (
    list_due_feeds,
    persist_feed_batch,
    record_feed_failure,
    sync_source_registry,
)
from curious_now_v2.pipeline.feed_reader import fetch_feed


@dataclass(frozen=True)
class IngestionRunResult:
    run_id: UUID
    feeds_attempted: int
    feeds_succeeded: int
    feeds_failed: int
    items_inserted: int
    items_updated: int
    stories_created: int


def _start_run(connection: psycopg.Connection[Any]) -> UUID:
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO pipeline_runs (job_name, status)
            VALUES ('ingest_once', 'running')
            RETURNING id;
            """
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("pipeline run insert returned no ID")
        return cast(UUID, row[0])


def _finish_run(
    connection: psycopg.Connection[Any],
    *,
    run_id: UUID,
    status: str,
    counters: dict[str, int],
    errors: tuple[str, ...],
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
            (
                status,
                Jsonb(counters),
                "\n".join(errors[:10]) or None,
                run_id,
            ),
        )


def run_ingestion_once(
    *,
    database_url: str,
    registry: SourceRegistry,
    limit: int = 25,
    timeout_seconds: float = 20,
) -> IngestionRunResult:
    """Sync the registry and collect due feeds in one observable batch."""

    with psycopg.connect(database_url, autocommit=True) as connection:
        sync_source_registry(connection, registry)
        now = datetime.now(UTC)
        due_feeds = list_due_feeds(connection, now=now, limit=limit)
        run_id = _start_run(connection)

        succeeded = 0
        failed = 0
        inserted = 0
        updated = 0
        stories = 0
        errors: list[str] = []

        timeout = httpx.Timeout(timeout_seconds)
        with httpx.Client(timeout=timeout) as client:
            for due in due_feeds:
                started_at = datetime.now(UTC)
                try:
                    batch = fetch_feed(
                        client=client,
                        source_id=due.source_id,
                        source=due.source,
                        feed=due.feed,
                        etag=due.etag,
                        last_modified=due.last_modified,
                    )
                    result = persist_feed_batch(
                        connection,
                        feed_id=due.feed_id,
                        batch=batch,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        pipeline_run_id=run_id,
                    )
                except Exception as exc:
                    failed += 1
                    message = f"{due.feed.url}: {type(exc).__name__}: {exc}"
                    errors.append(message)
                    record_feed_failure(
                        connection,
                        feed_id=due.feed_id,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        error=message,
                        pipeline_run_id=run_id,
                    )
                    continue

                succeeded += 1
                inserted += result.inserted_items
                updated += result.updated_items
                stories += result.created_stories

        counters = {
            "feeds_attempted": len(due_feeds),
            "feeds_succeeded": succeeded,
            "feeds_failed": failed,
            "items_inserted": inserted,
            "items_updated": updated,
            "stories_created": stories,
        }
        status = "partial" if failed and succeeded else "failed" if failed else "succeeded"
        _finish_run(
            connection,
            run_id=run_id,
            status=status,
            counters=counters,
            errors=tuple(errors),
        )

    return IngestionRunResult(
        run_id=run_id,
        feeds_attempted=len(due_feeds),
        feeds_succeeded=succeeded,
        feeds_failed=failed,
        items_inserted=inserted,
        items_updated=updated,
        stories_created=stories,
    )
