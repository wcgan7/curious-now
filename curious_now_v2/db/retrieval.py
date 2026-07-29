from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.core.enums import AccessClass, ContentType
from curious_now_v2.retrieval.document import Document
from curious_now_v2.retrieval.fetch import Fetcher
from curious_now_v2.retrieval.resolve import (
    Resolution,
    ResolutionStatus,
    TextKind,
    resolve_item_text,
)

# Paper-shaped content is worth resolving through open-access routes; anything
# else is only ever its own page.
PAPER_TYPES = frozenset(
    {
        ContentType.PREPRINT.value,
        ContentType.PEER_REVIEWED.value,
        ContentType.REPORT.value,
        ContentType.DATASET.value,
    }
)

RETRY_AFTER_DAYS = 14


@dataclass(frozen=True)
class RetrievalRunResult:
    attempted: int
    retrieved: int
    full_text: int
    abstract_only: int
    paywalled: int
    blocked: int
    failed: int


@dataclass(frozen=True)
class PendingItem:
    item_id: UUID
    url: str
    arxiv_id: str | None
    doi: str | None
    content_type: str


def list_items_needing_text(
    connection: psycopg.Connection[Any],
    *,
    limit: int,
) -> tuple[PendingItem, ...]:
    """Items never tried, or tried long enough ago to be worth retrying."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            -- Interleave sources so one large feed cannot fill the whole
            -- batch: everything shares a discovery timestamp, so ordering by
            -- date alone processes a single publisher for run after run.
            WITH candidates AS (
              SELECT
                id, url, arxiv_id, doi, content_type,
                row_number() OVER (
                  PARTITION BY source_id ORDER BY discovered_at DESC
                ) AS rank_in_source
              FROM items
              WHERE full_text IS NULL
                AND (
                  full_text_status = 'pending'
                  OR (
                    full_text_status IN ('not_found', 'error')
                    AND full_text_fetched_at < now() - %s::interval
                  )
                )
            )
            SELECT id, url, arxiv_id, doi, content_type
            FROM candidates
            ORDER BY rank_in_source, id
            LIMIT %s;
            """,
            (f"{RETRY_AFTER_DAYS} days", limit),
        )
        return tuple(
            PendingItem(
                item_id=row[0],
                url=row[1],
                arxiv_id=row[2],
                doi=row[3],
                content_type=row[4],
            )
            for row in cursor
        )


def structure_of(document: Document) -> dict[str, Any]:
    """The citation map: what sections and floats the text contains.

    Prose is stored once in full_text. This records where to point a reader,
    which is what Technical needs in order to cite a section or a figure.
    """

    return {
        "title": document.title,
        "abstract_words": len((document.abstract or "").split()),
        "extraction_method": document.extraction_method,
        "sections": [
            {
                "title": section.title,
                "kind": section.kind.value,
                "level": section.level,
                "words": section.word_count,
            }
            for section in document.sections
        ],
        "figures": [
            {"label": figure.label, "caption": figure.caption}
            for figure in document.figures
        ],
        "tables": [
            {"label": table.label, "caption": table.caption}
            for table in document.tables
        ],
    }


def store_resolution(
    connection: psycopg.Connection[Any],
    *,
    item_id: UUID,
    resolution: Resolution,
    now: datetime,
) -> None:
    """Persist the winning text and why the other candidates lost."""

    document = resolution.document
    text = document.text if document else None
    words = document.word_count if document else None

    # Access class only ever rises to what was actually retrieved.
    access_class: str | None = None
    if resolution.status is ResolutionStatus.OK:
        access_class = (
            AccessClass.OPEN_FULL_TEXT.value
            if resolution.kind is TextKind.FULL_TEXT
            else AccessClass.ABSTRACT.value
        )

    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE items SET
              full_text = %s,
              text_structure = %s,
              full_text_kind = %s,
              full_text_source = %s,
              full_text_status = %s,
              full_text_licence = %s,
              full_text_words = %s,
              full_text_score = %s,
              full_text_attempted = %s,
              full_text_error = %s,
              full_text_fetched_at = %s,
              access_class = CASE
                WHEN %s::text IS NULL THEN access_class
                WHEN %s::text = 'open_full_text' THEN 'open_full_text'
                WHEN access_class IN ('metadata_only', 'snippet') THEN %s::text
                ELSE access_class
              END,
              updated_at = now()
            WHERE id = %s;
            """,
            (
                text,
                Jsonb(structure_of(document) if document else {}),
                resolution.kind.value if resolution.kind else None,
                resolution.source,
                resolution.status.value,
                resolution.licence,
                words,
                resolution.score or None,
                Jsonb(list(resolution.reasons[:12])),
                resolution.error,
                now,
                access_class,
                access_class,
                access_class,
                item_id,
            ),
        )


def run_retrieval(
    database_url: str,
    *,
    limit: int = 50,
    timeout_seconds: float = 30,
) -> RetrievalRunResult:
    """Resolve full text for items that do not have any yet."""

    now = datetime.now(UTC)
    counts = dict.fromkeys(
        ("retrieved", "full_text", "abstract_only", "paywalled", "blocked", "failed"),
        0,
    )

    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_runs (job_name, status)
                VALUES ('retrieve', 'running')
                RETURNING id;
                """
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("pipeline run insert returned no ID")
            run_id = cast(UUID, row[0])

        pending = list_items_needing_text(connection, limit=limit)
        with Fetcher(timeout_seconds=timeout_seconds) as fetcher:
            for item in pending:
                resolution = resolve_item_text(
                    fetcher,
                    url=item.url,
                    arxiv_id=item.arxiv_id,
                    doi=item.doi,
                    is_paper=item.content_type in PAPER_TYPES,
                )
                store_resolution(
                    connection,
                    item_id=item.item_id,
                    resolution=resolution,
                    now=now,
                )
                if resolution.status is ResolutionStatus.OK:
                    counts["retrieved"] += 1
                    if resolution.kind is TextKind.FULL_TEXT:
                        counts["full_text"] += 1
                    else:
                        counts["abstract_only"] += 1
                elif resolution.status is ResolutionStatus.PAYWALLED:
                    counts["paywalled"] += 1
                elif resolution.status is ResolutionStatus.BLOCKED:
                    counts["blocked"] += 1
                else:
                    counts["failed"] += 1

        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_runs SET
                  status = %s,
                  finished_at = now(),
                  counters = %s
                WHERE id = %s;
                """,
                (
                    "succeeded" if counts["retrieved"] else "partial",
                    Jsonb({"attempted": len(pending), **counts}),
                    run_id,
                ),
            )

    return RetrievalRunResult(attempted=len(pending), **counts)
