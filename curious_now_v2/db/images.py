"""Backfill publisher-declared images from retrieval bodies already stored."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.core import blobs
from curious_now_v2.retrieval.document import Figure
from curious_now_v2.retrieval.extract_jats import extract_jats
from curious_now_v2.retrieval.images import extract_html_preview_image


@dataclass(frozen=True)
class ImageBackfillResult:
    scanned: int
    candidates: int
    updated: int
    figure_items: int
    preview_items: int
    no_image: int
    missing_blobs: int
    failed: int
    hosts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class _Fetch:
    source: str
    parser: str
    url: str
    final_url: str | None
    digest: str


@dataclass(frozen=True)
class _Item:
    item_id: UUID
    url: str
    structure: dict[str, Any]
    fetches: tuple[_Fetch, ...]


def _normal_label(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def merge_figure_images(
    structure: dict[str, Any],
    figures: tuple[Figure, ...],
) -> tuple[dict[str, Any], int]:
    """Attach recovered URLs to the corresponding stored figure records."""

    raw = structure.get("figures")
    if not isinstance(raw, list) or not raw:
        return structure, 0

    candidates = [figure for figure in figures if figure.image_url]
    if not candidates:
        return structure, 0

    enriched = deepcopy(structure)
    stored = enriched.get("figures")
    if not isinstance(stored, list):
        return structure, 0

    used: set[int] = set()
    changed = 0
    for position, entry in enumerate(stored):
        if not isinstance(entry, dict) or entry.get("image_url"):
            continue
        label = _normal_label(entry.get("label"))
        match = next(
            (
                index
                for index, figure in enumerate(candidates)
                if index not in used
                and label
                and _normal_label(figure.label) == label
            ),
            None,
        )
        if match is None and position < len(candidates) and position not in used:
            match = position
        if match is None:
            match = next(
                (index for index in range(len(candidates)) if index not in used),
                None,
            )
        if match is None:
            break
        entry["image_url"] = candidates[match].image_url
        used.add(match)
        changed += 1
    return (enriched, changed) if changed else (structure, 0)


def _load_items(
    connection: psycopg.Connection[Any], *, limit: int
) -> tuple[_Item, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH targets AS (
              SELECT DISTINCT i.id, i.url, i.text_structure
              FROM items i
              JOIN story_items si ON si.item_id = i.id
              JOIN stories s ON s.id = si.story_id
              WHERE s.status = 'published'
                AND s.withheld_kind IS NULL
                AND i.image_url IS NULL
                AND NOT EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements(
                    COALESCE(i.text_structure->'figures', '[]'::jsonb)
                  ) figure
                  WHERE NULLIF(figure->>'image_url', '') IS NOT NULL
                )
              ORDER BY i.id
              LIMIT %s
            )
            SELECT t.id, t.url, t.text_structure,
                   f.source, f.parser, f.url, f.final_url, f.body_sha256
            FROM targets t
            LEFT JOIN item_fetches f ON f.item_id = t.id
            ORDER BY t.id,
              CASE f.parser WHEN 'jats' THEN 1 WHEN 'article' THEN 2 ELSE 3 END,
              f.fetched_at DESC;
            """,
            (limit,),
        )
        rows = cursor.fetchall()

    grouped: dict[UUID, tuple[str, dict[str, Any], list[_Fetch]]] = {}
    for row in rows:
        item_id = cast(UUID, row[0])
        if item_id not in grouped:
            grouped[item_id] = (
                str(row[1]),
                cast(dict[str, Any], row[2] if isinstance(row[2], dict) else {}),
                [],
            )
        if row[3] is not None:
            grouped[item_id][2].append(
                _Fetch(
                    source=str(row[3]),
                    parser=str(row[4]),
                    url=str(row[5]),
                    final_url=str(row[6]) if row[6] else None,
                    digest=str(row[7]),
                )
            )
    return tuple(
        _Item(item_id, url, structure, tuple(fetches))
        for item_id, (url, structure, fetches) in grouped.items()
    )


def _candidate(
    item: _Item,
) -> tuple[str | None, dict[str, Any] | None, int, int, bool]:
    """Return preview URL or enriched structure and diagnostic counts."""

    missing = 0
    for fetch in item.fetches:
        if fetch.parser != "jats":
            continue
        body = blobs.get(fetch.digest)
        if body is None:
            missing += 1
            continue
        document = extract_jats(
            body.decode("utf-8", errors="replace"),
            source=fetch.source,
            base_url=fetch.url,
        )
        figures = tuple(figure for figure in document.figures if figure.image_url)
        if not figures:
            continue
        structure, changed = merge_figure_images(item.structure, figures)
        if changed:
            return None, structure, changed, missing, False
        # A structured copy can contain a figure even when a different winning
        # copy supplied no figure map. It is still the same source work, so its
        # first figure is an honest preview.
        return figures[0].image_url, None, 0, missing, False

    for fetch in item.fetches:
        if fetch.parser != "article":
            continue
        body = blobs.get(fetch.digest)
        if body is None:
            missing += 1
            continue
        image = extract_html_preview_image(
            body.decode("utf-8", errors="replace"),
            base_url=fetch.final_url or fetch.url or item.url,
        )
        if image:
            return image, None, 0, missing, False
    return None, None, 0, missing, True


def run_image_backfill(
    database_url: str,
    *,
    limit: int = 1000,
    dry_run: bool = False,
) -> ImageBackfillResult:
    """Enrich published items from existing blobs without publisher requests."""

    hosts: Counter[str] = Counter()
    counts = Counter[str]()
    with psycopg.connect(database_url, autocommit=True) as connection:
        run_id: UUID | None = None
        if not dry_run:
            with connection.transaction(), connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO pipeline_runs (job_name, status)
                    VALUES ('image_backfill', 'running') RETURNING id;
                    """
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("pipeline run insert returned no ID")
                run_id = cast(UUID, row[0])

        items = _load_items(connection, limit=limit)
        for item in items:
            try:
                image, structure, changed, missing, absent = _candidate(item)
                counts["missing_blobs"] += missing
                if absent:
                    counts["no_image"] += 1
                    continue
                counts["candidates"] += 1
                candidate_url = image
                if structure is not None:
                    raw_figures = structure.get("figures")
                    if isinstance(raw_figures, list):
                        candidate_url = next(
                            (
                                str(figure.get("image_url"))
                                for figure in raw_figures
                                if isinstance(figure, dict)
                                and figure.get("image_url")
                            ),
                            None,
                        )
                if candidate_url:
                    hosts[urlsplit(candidate_url).hostname or "invalid"] += 1
                if dry_run:
                    if structure is not None:
                        counts["figure_items"] += 1
                    else:
                        counts["preview_items"] += 1
                    continue

                with connection.transaction(), connection.cursor() as cursor:
                    if structure is not None:
                        cursor.execute(
                            """
                            UPDATE items SET text_structure = %s, updated_at = now()
                            WHERE id = %s;
                            """,
                            (Jsonb(structure), item.item_id),
                        )
                        counts["figure_items"] += 1
                        counts["updated"] += bool(cursor.rowcount)
                    elif image:
                        cursor.execute(
                            """
                            UPDATE items SET image_url = %s, updated_at = now()
                            WHERE id = %s AND image_url IS NULL;
                            """,
                            (image, item.item_id),
                        )
                        counts["preview_items"] += 1
                        counts["updated"] += bool(cursor.rowcount)
            except Exception:  # noqa: BLE001 — one malformed body cannot stop a corpus
                counts["failed"] += 1

        if run_id is not None:
            payload = {
                "scanned": len(items),
                **{name: counts[name] for name in (
                    "candidates",
                    "updated",
                    "figure_items",
                    "preview_items",
                    "no_image",
                    "missing_blobs",
                    "failed",
                )},
                "hosts": dict(hosts),
            }
            with connection.transaction(), connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE pipeline_runs SET status = %s, finished_at = now(),
                      counters = %s WHERE id = %s;
                    """,
                    (
                        "succeeded" if not counts["failed"] else "partial",
                        Jsonb(payload),
                        run_id,
                    ),
                )

    return ImageBackfillResult(
        scanned=len(items),
        candidates=counts["candidates"],
        updated=counts["updated"],
        figure_items=counts["figure_items"],
        preview_items=counts["preview_items"],
        no_image=counts["no_image"],
        missing_blobs=counts["missing_blobs"],
        failed=counts["failed"],
        hosts=tuple(hosts.most_common()),
    )
