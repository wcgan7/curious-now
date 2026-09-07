from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.core import blobs
from curious_now_v2.core.enums import AccessClass, ContentType
from curious_now_v2.retrieval.document import Document, Reference
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
    source: str | None = None,
    refetch_source: str | None = None,
    refetch_path: str | None = None,
) -> tuple[PendingItem, ...]:
    """Items never tried, or tried long enough ago to be worth retrying.

    `refetch_source` and `refetch_path` reopen items that already have text,
    which the normal queue never does — it selects on `full_text IS NULL`, so a
    fix to an extractor reaches everything that arrives afterwards and nothing
    already held. Recovering arXiv's display equations changed what the
    LaTeXML path produces and left all 45 stored arXiv papers exactly as they
    were, still missing the mathematics their prose discusses.
    """

    if refetch_source or refetch_path:
        return _list_items_to_refetch(
            connection, limit=limit, source=refetch_source, path=refetch_path
        )

    source_clause = ""
    parameters: list[object] = []
    if source:
        source_clause = "AND source_id = (SELECT id FROM sources WHERE name = %s)"
        parameters.append(source)
    parameters.append(f"{RETRY_AFTER_DAYS} days")
    parameters.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
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
                -- A source dropped for never returning anything must stop
                -- being asked; its backlog outlives the decision otherwise.
                AND source_id IN (SELECT id FROM sources WHERE active)
                {source_clause}
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
            tuple(parameters),
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


def _list_items_to_refetch(
    connection: psycopg.Connection[Any],
    *,
    limit: int,
    source: str | None,
    path: str | None,
) -> tuple[PendingItem, ...]:
    """Items whose text should be extracted again from the same source.

    Deliberately narrow, and never automatic. Re-extraction costs a request to
    a publisher for text we already hold, so it is asked for by name — a source
    or an extraction path — when a change to that path makes the stored version
    wrong rather than merely older.
    """

    clauses = ["i.full_text IS NOT NULL"]
    parameters: list[object] = []
    if source:
        clauses.append("src.name = %s")
        parameters.append(source)
    if path:
        clauses.append("i.full_text_source = %s")
        parameters.append(path)
    parameters.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT i.id, i.url, i.arxiv_id, i.doi, i.content_type
            FROM items i
            JOIN sources src ON src.id = i.source_id
            WHERE {" AND ".join(clauses)}
              AND src.active
            ORDER BY i.full_text_fetched_at ASC NULLS FIRST, i.id
            LIMIT %s;
            """,
            tuple(parameters),
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
            {
                "label": figure.label,
                "caption": figure.caption,
                "image_url": figure.image_url,
            }
            for figure in document.figures
        ],
        "tables": [
            {"label": table.label, "caption": table.caption}
            for table in document.tables
        ],
    }


# Postgres text cannot hold a NUL, and one arriving from a publisher's markup
# would abort the transaction that also carries the item's full text.
_UNSTORABLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _storable(value: str) -> str:
    return _UNSTORABLE.sub("", value)


def _store_fetches(
    cursor: psycopg.Cursor[Any], *, item_id: UUID, resolution: Resolution
) -> None:
    """Record what this resolution fetched, and put the bodies in the store.

    The blob is written before the row that points at it. A crash between the
    two leaves an orphaned file, which a sweep can collect; the reverse order
    would leave a row pointing at nothing, which every reader would then have to
    treat as corruption.

    A body that cannot be stored is skipped rather than raised on. The blob root
    is an external disk, and an unmounted drive must not cost an item the text
    and references that were successfully extracted from it.
    """

    cursor.execute("DELETE FROM item_fetches WHERE item_id = %s;", (item_id,))
    if not resolution.fetches:
        return

    rows = []
    for fetch in resolution.fetches:
        if not fetch.body:
            continue
        try:
            stored = blobs.put(fetch.body)
        except OSError:
            continue
        rows.append(
            (
                item_id,
                fetch.source,
                fetch.parser,
                fetch.url,
                fetch.final_url,
                fetch.status_code,
                fetch.content_type,
                stored.digest,
                stored.raw_bytes,
            )
        )
    if not rows:
        return

    cursor.executemany(
        """
        INSERT INTO item_fetches (
          item_id, source, parser, url, final_url, status_code,
          content_type, body_sha256, body_bytes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (item_id, source) DO NOTHING;
        """,
        rows,
    )


def _store_references(
    cursor: psycopg.Cursor[Any], *, item_id: UUID, resolution: Resolution
) -> None:
    """Replace an item's bibliography with what this resolution recovered.

    Deleting first makes re-extraction idempotent: a re-fetch that recovers
    more references, or renumbers them, must not leave the previous run's rows
    behind to be counted twice by the ranking that reads `mentions`.
    """

    cursor.execute("DELETE FROM item_references WHERE item_id = %s;", (item_id,))
    if not resolution.references or not resolution.reference_source:
        return

    # A document that hands us the same anchor twice must not cost the item its
    # full text: this insert shares a transaction with the text above, so one
    # duplicate key would roll back the whole retrieval. Extractors are expected
    # to emit unique keys, and this is the backstop for when one does not.
    unique: dict[str, Reference] = {}
    for reference in resolution.references:
        unique.setdefault(reference.key, reference)
    references = list(unique.values())

    cursor.executemany(
        """
        INSERT INTO item_references (
          item_id, reference_source, ref_key, label, citation_text,
          doi, arxiv_id, mentions, cited_sections, contexts
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        [
            (
                item_id,
                resolution.reference_source,
                _storable(reference.key),
                _storable(reference.label) if reference.label else None,
                _storable(reference.text),
                reference.doi,
                reference.arxiv_id,
                reference.mentions,
                sorted(kind.value for kind in reference.cited_in),
                Jsonb(
                    [
                        {
                            "section": context.section.value,
                            "sentence": _storable(context.sentence),
                        }
                        for context in reference.contexts
                    ]
                ),
            )
            for reference in references
        ],
    )


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
              image_url = COALESCE(image_url, %s),
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
                resolution.image_url,
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
        _store_references(cursor, item_id=item_id, resolution=resolution)
        _store_fetches(cursor, item_id=item_id, resolution=resolution)


def run_retrieval(
    database_url: str,
    *,
    limit: int = 50,
    timeout_seconds: float = 30,
    source: str | None = None,
    refetch_source: str | None = None,
    refetch_path: str | None = None,
) -> RetrievalRunResult:
    """Resolve full text for items that do not have any yet.

    With `refetch_source` or `refetch_path`, resolve it again for items that
    already have text, so a fix to an extractor can reach what is already
    stored.
    """

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

        pending = list_items_needing_text(
            connection,
            limit=limit,
            source=source,
            refetch_source=refetch_source,
            refetch_path=refetch_path,
        )
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
