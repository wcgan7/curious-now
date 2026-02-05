from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

import psycopg

from curious_now.api.schemas import (
    FeedType,
    ImportSourcePackResponse,
    Item,
    ItemsFeedResponse,
    ItemSource,
    PatchFeedRequest,
    PatchSourceRequest,
    ReliabilityTier,
    Source,
    SourceFeedHealth,
    SourcePack,
    SourcesResponse,
    SourcesResponseRow,
    SourceType,
)


def list_sources(conn: psycopg.Connection[Any]) -> SourcesResponse:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              s.id AS source_id,
              s.name,
              s.homepage_url,
              s.source_type,
              s.reliability_tier,
              s.active,
              f.id AS feed_id,
              f.feed_url,
              f.feed_type,
              f.fetch_interval_minutes,
              f.last_fetched_at,
              f.last_status,
              f.error_streak,
              f.active AS feed_active
            FROM sources s
            LEFT JOIN source_feeds f ON f.source_id = s.id
            ORDER BY s.name ASC, f.feed_url ASC;
            """
        )
        rows = cur.fetchall()

    by_source: dict[UUID, dict[str, Any]] = {}
    feeds_by_source: dict[UUID, list[SourceFeedHealth]] = defaultdict(list)

    for r in rows:
        sid = r["source_id"]
        if sid not in by_source:
            by_source[sid] = {
                "source_id": sid,
                "name": r["name"],
                "homepage_url": r["homepage_url"],
                "source_type": r["source_type"],
                "reliability_tier": r["reliability_tier"],
                "active": r["active"],
            }
        if r["feed_id"] is not None:
            feeds_by_source[sid].append(
                SourceFeedHealth(
                    feed_id=r["feed_id"],
                    feed_url=r["feed_url"],
                    feed_type=r["feed_type"],
                    active=r["feed_active"],
                    fetch_interval_minutes=r["fetch_interval_minutes"],
                    last_fetched_at=r["last_fetched_at"],
                    last_status=r["last_status"],
                    error_streak=r["error_streak"],
                )
            )

    sources: list[SourcesResponseRow] = []
    for sid, srow in by_source.items():
        sources.append(
            SourcesResponseRow(source=Source(**srow), feeds=feeds_by_source.get(sid, []))
        )

    return SourcesResponse(sources=sources)


def list_items_feed(
    conn: psycopg.Connection[Any],
    *,
    page: int,
    page_size: int,
    source_id: UUID | None,
    content_type: str | None,
) -> ItemsFeedResponse:
    offset = (page - 1) * page_size
    where: list[str] = []
    params: list[Any] = []
    if source_id:
        where.append("i.source_id = %s")
        params.append(source_id)
    if content_type:
        where.append("i.content_type = %s")
        params.append(content_type)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              i.id AS item_id,
              i.canonical_url,
              i.url,
              i.title,
              i.snippet,
              i.author,
              i.published_at,
              i.fetched_at,
              i.content_type,
              i.paywalled,
              i.arxiv_id,
              i.doi,
              i.pmid,
              s.id AS source_id,
              s.name AS source_name
            FROM items i
            JOIN sources s ON s.id = i.source_id
            {where_sql}
            ORDER BY i.published_at DESC NULLS LAST, i.fetched_at DESC
            LIMIT %s OFFSET %s;
            """,
            (*params, page_size, offset),
        )
        rows = cur.fetchall()

    results: list[Item] = []
    for r in rows:
        results.append(
            Item(
                item_id=r["item_id"],
                canonical_url=r["canonical_url"],
                url=r["url"],
                title=r["title"],
                snippet=r["snippet"],
                author=r["author"],
                published_at=r["published_at"],
                fetched_at=r["fetched_at"],
                content_type=r["content_type"],
                paywalled=r["paywalled"],
                source=ItemSource(source_id=r["source_id"], name=r["source_name"]),
                arxiv_id=r["arxiv_id"],
                doi=r["doi"],
                pmid=r["pmid"],
            )
        )

    return ItemsFeedResponse(page=page, results=results)


def import_source_pack(conn: psycopg.Connection[Any], pack: SourcePack) -> ImportSourcePackResponse:
    sources_upserted = 0
    feeds_upserted = 0
    with conn.cursor() as cur:
        for s in pack.sources:
            cur.execute(
                """
                INSERT INTO sources(
                  name, homepage_url, source_type, reliability_tier, terms_notes, active
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (name)
                DO UPDATE SET
                  homepage_url = EXCLUDED.homepage_url,
                  source_type = EXCLUDED.source_type,
                  reliability_tier = EXCLUDED.reliability_tier,
                  terms_notes = EXCLUDED.terms_notes,
                  active = EXCLUDED.active
                RETURNING id;
                """,
                (
                    s.name,
                    s.homepage_url,
                    s.source_type.value,
                    s.reliability_tier.value if s.reliability_tier else None,
                    s.terms_notes,
                    s.active,
                ),
            )
            row = cur.fetchone()
            if row:
                source_id = row["id"]
                sources_upserted += 1
            else:
                # Should not happen with RETURNING.
                continue

            for f in s.feeds:
                cur.execute(
                    """
                    INSERT INTO source_feeds(
                      source_id, feed_url, feed_type, fetch_interval_minutes, active
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (source_id, feed_url)
                    DO UPDATE SET
                      feed_type = EXCLUDED.feed_type,
                      fetch_interval_minutes = EXCLUDED.fetch_interval_minutes,
                      active = EXCLUDED.active;
                    """,
                    (
                        source_id,
                        f.feed_url,
                        f.feed_type.value,
                        f.fetch_interval_minutes,
                        f.active,
                    ),
                )
                feeds_upserted += 1

    return ImportSourcePackResponse(
        sources_upserted=sources_upserted, feeds_upserted=feeds_upserted
    )


def patch_source(
    conn: psycopg.Connection[Any], *, source_id: UUID, patch: PatchSourceRequest
) -> Source:
    fields: list[str] = []
    params: list[Any] = []
    fields_set = patch.model_fields_set
    for col in ["name", "homepage_url", "source_type", "reliability_tier", "terms_notes", "active"]:
        if col not in fields_set:
            continue
        value = getattr(patch, col)
        if value is None and col in {"name", "source_type", "active"}:
            raise ValueError(f"{col} cannot be null")
        fields.append(f"{col} = %s")
        params.append(value.value if hasattr(value, "value") else value)
    with conn.cursor() as cur:
        if fields:
            params.append(source_id)
            cur.execute(f"UPDATE sources SET {', '.join(fields)} WHERE id = %s;", params)
        cur.execute(
            """
            SELECT id AS source_id, name, homepage_url, source_type, reliability_tier, active
            FROM sources
            WHERE id = %s;
            """,
            (source_id,),
        )
        row = cur.fetchone()
    if not row:
        raise KeyError("source not found")
    return Source(
        source_id=row["source_id"],
        name=row["name"],
        homepage_url=row["homepage_url"],
        source_type=SourceType(row["source_type"]),
        reliability_tier=(
            ReliabilityTier(row["reliability_tier"]) if row["reliability_tier"] else None
        ),
        active=row["active"],
    )


def patch_feed(
    conn: psycopg.Connection[Any], *, feed_id: UUID, patch: PatchFeedRequest
) -> SourceFeedHealth:
    fields: list[str] = []
    params: list[Any] = []
    fields_set = patch.model_fields_set
    for col in ["feed_url", "feed_type", "fetch_interval_minutes", "active"]:
        if col not in fields_set:
            continue
        value = getattr(patch, col)
        if value is None:
            raise ValueError(f"{col} cannot be null")
        fields.append(f"{col} = %s")
        params.append(value.value if hasattr(value, "value") else value)
    with conn.cursor() as cur:
        if fields:
            params.append(feed_id)
            cur.execute(f"UPDATE source_feeds SET {', '.join(fields)} WHERE id = %s;", params)
        cur.execute(
            """
            SELECT
              id AS feed_id,
              feed_url,
              feed_type,
              fetch_interval_minutes,
              last_fetched_at,
              last_status,
              error_streak,
              active
            FROM source_feeds
            WHERE id = %s;
            """,
            (feed_id,),
        )
        row = cur.fetchone()
    if not row:
        raise KeyError("feed not found")
    return SourceFeedHealth(
        feed_id=row["feed_id"],
        feed_url=row["feed_url"],
        feed_type=FeedType(row["feed_type"]),
        active=row["active"],
        fetch_interval_minutes=row["fetch_interval_minutes"],
        last_fetched_at=row["last_fetched_at"],
        last_status=row["last_status"],
        error_streak=row["error_streak"],
    )
