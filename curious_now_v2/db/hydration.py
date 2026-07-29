from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import httpx
import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.pipeline.hydrate import (
    ARXIV_API,
    ARXIV_BATCH_SIZE,
    CROSSREF_API,
    PaperHydration,
    arxiv_batches,
    parse_arxiv_response,
    parse_crossref_work,
)

USER_AGENT = "CuriousNow/2 (+https://github.com/curious-now)"

# arXiv asks for a few seconds between programmatic queries.
ARXIV_DELAY_SECONDS = 3.0

# Many DOIs never publish an abstract. Retry eventually, since a provider may
# deposit one later, but not on every run.
RETRY_AFTER_DAYS = 7


@dataclass(frozen=True)
class HydrationRunResult:
    papers_attempted: int
    papers_hydrated: int
    papers_without_abstract: int
    papers_failed: int
    items_upgraded: int


@dataclass(frozen=True)
class PendingPaper:
    paper_id: UUID
    arxiv_id: str | None
    doi: str | None


def list_papers_needing_abstracts(
    connection: psycopg.Connection[Any],
    *,
    limit: int,
) -> tuple[PendingPaper, ...]:
    """Find papers with an identifier but no stored abstract.

    arXiv-identified and DOI-only papers are selected separately so one
    provider cannot starve the other: ingesting a large batch from a single
    source would otherwise fill the whole window in creation order.
    """

    def select(condition: str, count: int) -> list[PendingPaper]:
        if count < 1:
            return []
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, arxiv_id, doi
                FROM papers
                WHERE abstract IS NULL AND {condition}
                  AND (
                    metadata->>'hydration_attempted_at' IS NULL
                    OR (metadata->>'hydration_attempted_at')::timestamptz
                       < now() - %s::interval
                  )
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (f"{RETRY_AFTER_DAYS} days", count),
            )
            return [
                PendingPaper(paper_id=row[0], arxiv_id=row[1], doi=row[2])
                for row in cursor
            ]

    half = max(limit // 2, 1)
    arxiv = select("arxiv_id IS NOT NULL", half)
    doi_only = select("arxiv_id IS NULL AND doi IS NOT NULL", limit - len(arxiv))
    # Backfill from whichever pool still has work when the other runs dry.
    if len(arxiv) + len(doi_only) < limit and len(arxiv) == half:
        arxiv = select("arxiv_id IS NOT NULL", limit - len(doi_only))
    return tuple((*arxiv, *doi_only))


def _record_attempt(
    connection: psycopg.Connection[Any],
    *,
    paper_ids: list[UUID],
    now: datetime,
) -> None:
    """Stamp papers that yielded no abstract so they are not retried at once."""

    if not paper_ids:
        return
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE papers SET
              metadata = metadata || %s,
              updated_at = now()
            WHERE id = ANY(%s);
            """,
            (Jsonb({"hydration_attempted_at": now.isoformat()}), paper_ids),
        )


def _store_hydration(
    connection: psycopg.Connection[Any],
    *,
    paper_id: UUID,
    hydration: PaperHydration,
    now: datetime,
) -> int:
    """Persist an abstract and lift the access class of its linked items."""

    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE papers SET
              abstract = %s,
              access_class = %s,
              metadata = metadata || %s,
              updated_at = now()
            WHERE id = %s;
            """,
            (
                hydration.abstract,
                hydration.access_class.value,
                Jsonb(
                    {
                        "extraction_method": hydration.extraction_method,
                        "hydrated_at": now.isoformat(),
                    }
                ),
                paper_id,
            ),
        )
        # Items keep their own access class; hydration only ever raises it from
        # metadata/snippet to abstract, never past what was actually fetched.
        cursor.execute(
            """
            UPDATE items SET
              access_class = %s,
              updated_at = now()
            WHERE id IN (SELECT item_id FROM item_papers WHERE paper_id = %s)
              AND access_class IN ('metadata_only', 'snippet');
            """,
            (hydration.access_class.value, paper_id),
        )
        return cursor.rowcount


def _fetch_arxiv(
    client: httpx.Client,
    arxiv_ids: tuple[str, ...],
) -> dict[str, PaperHydration]:
    response = client.get(
        ARXIV_API,
        params={
            "id_list": ",".join(arxiv_ids),
            "max_results": str(ARXIV_BATCH_SIZE),
        },
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return parse_arxiv_response(response.content)


def _fetch_crossref(client: httpx.Client, doi: str) -> PaperHydration | None:
    response = client.get(
        f"{CROSSREF_API}/{doi}",
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )
    if response.status_code == httpx.codes.NOT_FOUND:
        return None
    response.raise_for_status()
    return parse_crossref_work(response.json())


def run_hydration(
    database_url: str,
    *,
    limit: int = 100,
    timeout_seconds: float = 30,
    sleep: bool = True,
) -> HydrationRunResult:
    """Fetch abstracts for papers that have an identifier but no text.

    Hydration failure never blocks an item or its story; the paper simply
    keeps its previous access class.
    """

    now = datetime.now(UTC)
    hydrated = 0
    without_abstract = 0
    failed = 0
    upgraded = 0

    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_runs (job_name, status)
                VALUES ('hydrate', 'running')
                RETURNING id;
                """
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("pipeline run insert returned no ID")
            run_id = cast(UUID, row[0])

        pending = list_papers_needing_abstracts(connection, limit=limit)
        by_arxiv = {
            paper.arxiv_id.casefold(): paper
            for paper in pending
            if paper.arxiv_id
        }
        doi_only = [
            paper for paper in pending if not paper.arxiv_id and paper.doi
        ]
        errors: list[str] = []
        no_abstract: list[UUID] = []

        with httpx.Client(timeout=httpx.Timeout(timeout_seconds)) as client:
            batches = arxiv_batches(tuple(by_arxiv))
            for index, batch in enumerate(batches):
                if index and sleep:
                    time.sleep(ARXIV_DELAY_SECONDS)
                try:
                    found = _fetch_arxiv(client, batch)
                except Exception as exc:
                    failed += len(batch)
                    errors.append(f"arxiv batch: {type(exc).__name__}: {exc}")
                    continue
                for arxiv_id in batch:
                    hydration = found.get(arxiv_id.casefold())
                    paper = by_arxiv[arxiv_id.casefold()]
                    if hydration is None:
                        without_abstract += 1
                        no_abstract.append(paper.paper_id)
                        continue
                    upgraded += _store_hydration(
                        connection,
                        paper_id=paper.paper_id,
                        hydration=hydration,
                        now=now,
                    )
                    hydrated += 1

            for paper in doi_only:
                if paper.doi is None:
                    continue
                try:
                    hydration = _fetch_crossref(client, paper.doi)
                except Exception as exc:
                    failed += 1
                    errors.append(f"{paper.doi}: {type(exc).__name__}: {exc}")
                    continue
                if hydration is None:
                    # Many DOIs are news or editorial items that legitimately
                    # publish no abstract; that is not a fetch failure.
                    without_abstract += 1
                    no_abstract.append(paper.paper_id)
                    continue
                upgraded += _store_hydration(
                    connection,
                    paper_id=paper.paper_id,
                    hydration=hydration,
                    now=now,
                )
                hydrated += 1

        _record_attempt(connection, paper_ids=no_abstract, now=now)

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
                    "partial" if failed and hydrated else
                    "failed" if failed and not hydrated else "succeeded",
                    Jsonb(
                        {
                            "papers_attempted": len(pending),
                            "papers_hydrated": hydrated,
                            "papers_without_abstract": without_abstract,
                            "papers_failed": failed,
                            "items_upgraded": upgraded,
                        }
                    ),
                    "\n".join(errors[:10]) or None,
                    run_id,
                ),
            )

    return HydrationRunResult(
        papers_attempted=len(pending),
        papers_hydrated=hydrated,
        papers_without_abstract=without_abstract,
        papers_failed=failed,
        items_upgraded=upgraded,
    )
