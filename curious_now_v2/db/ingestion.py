from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

from curious_now_v2.core.enums import (
    ContentType,
    SourceRole,
    StoryItemRole,
)
from curious_now_v2.core.source_registry import (
    ContentTypeRule,
    FeedSpec,
    SourcePolicy,
    SourceRegistry,
    SourceSpec,
)
from curious_now_v2.pipeline.feed_reader import FeedBatch
from curious_now_v2.pipeline.ingest import IngestCandidate


class DueFeed(BaseModel):
    model_config = ConfigDict(frozen=True)

    feed_id: UUID
    source_id: UUID
    source: SourceSpec
    feed: FeedSpec
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True)
class RegistrySyncResult:
    sources: int
    feeds: int


@dataclass(frozen=True)
class PersistBatchResult:
    inserted_items: int
    updated_items: int
    created_stories: int
    attached_items: int


def sync_source_registry(
    connection: psycopg.Connection[Any],
    registry: SourceRegistry,
) -> RegistrySyncResult:
    """Upsert configured sources without conflating policy and fetch state."""

    feed_count = 0
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE source_feeds
            SET active = FALSE, updated_at = now()
            WHERE active = TRUE;
            """
        )
        cursor.execute(
            """
            UPDATE sources
            SET active = FALSE, updated_at = now()
            WHERE active = TRUE;
            """
        )
        for source in registry.sources:
            cursor.execute(
                """
                INSERT INTO sources (name, homepage_url, role, active, policy)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                  homepage_url = EXCLUDED.homepage_url,
                  role = EXCLUDED.role,
                  active = EXCLUDED.active,
                  policy = EXCLUDED.policy,
                  updated_at = now()
                RETURNING id;
                """,
                (
                    source.name,
                    source.homepage_url,
                    source.role.value,
                    source.active,
                    Jsonb(source.policy.model_dump(mode="json")),
                ),
            )
            source_row = cursor.fetchone()
            if source_row is None:
                raise RuntimeError(f"source upsert returned no ID for {source.name}")
            source_id = source_row[0]

            for feed in source.feeds:
                cursor.execute(
                    """
                    INSERT INTO source_feeds (
                      source_id,
                      url,
                      feed_kind,
                      default_content_type,
                      content_type_rules,
                      exclude_patterns,
                      max_entries,
                      fetch_interval_minutes,
                      active,
                      next_fetch_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (url) DO UPDATE SET
                      source_id = EXCLUDED.source_id,
                      feed_kind = EXCLUDED.feed_kind,
                      default_content_type = EXCLUDED.default_content_type,
                      content_type_rules = EXCLUDED.content_type_rules,
                      exclude_patterns = EXCLUDED.exclude_patterns,
                      max_entries = EXCLUDED.max_entries,
                      fetch_interval_minutes = EXCLUDED.fetch_interval_minutes,
                      active = EXCLUDED.active,
                      updated_at = now();
                    """,
                    (
                        source_id,
                        feed.url,
                        feed.kind.value,
                        feed.default_content_type.value,
                        Jsonb([rule.model_dump(mode="json")
                               for rule in feed.content_type_rules]),
                        Jsonb(list(feed.exclude_patterns)),
                        feed.max_entries,
                        feed.fetch_interval_minutes,
                        source.active,
                    ),
                )
                feed_count += 1

    return RegistrySyncResult(sources=len(registry.sources), feeds=feed_count)


def list_due_feeds(
    connection: psycopg.Connection[Any],
    *,
    now: datetime,
    limit: int,
) -> tuple[DueFeed, ...]:
    """Lock-free due-feed read; one scheduled worker is the initial target."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              f.id,
              f.source_id,
              f.url,
              f.feed_kind,
              f.default_content_type,
              f.content_type_rules,
              f.exclude_patterns,
              f.max_entries,
              f.fetch_interval_minutes,
              f.etag,
              f.last_modified,
              s.name,
              s.homepage_url,
              s.role,
              s.policy
            FROM source_feeds f
            JOIN sources s ON s.id = f.source_id
            WHERE f.active = TRUE
              AND s.active = TRUE
              AND (f.next_fetch_at IS NULL OR f.next_fetch_at <= %s)
            ORDER BY f.next_fetch_at ASC NULLS FIRST, f.id ASC
            LIMIT %s;
            """,
            (now, limit),
        )
        rows = cursor.fetchall()

    due: list[DueFeed] = []
    for row in rows:
        feed = FeedSpec(
            url=row[2],
            kind=row[3],
            default_content_type=row[4],
            content_type_rules=tuple(
                ContentTypeRule.model_validate(rule) for rule in (row[5] or [])
            ),
            exclude_patterns=tuple(row[6] or ()),
            max_entries=row[7],
            fetch_interval_minutes=row[8],
        )
        source = SourceSpec(
            name=row[11],
            homepage_url=row[12],
            role=row[13],
            feeds=(feed,),
            policy=SourcePolicy.model_validate(row[14]),
        )
        due.append(
            DueFeed(
                feed_id=row[0],
                source_id=row[1],
                source=source,
                feed=feed,
                etag=row[9],
                last_modified=row[10],
            )
        )
    return tuple(due)


def _story_item_role(candidate: IngestCandidate) -> StoryItemRole:
    if candidate.content_type in {
        ContentType.PREPRINT,
        ContentType.PEER_REVIEWED,
    }:
        return StoryItemRole.PRIMARY_EVIDENCE
    if candidate.source_role is SourceRole.JOURNALISM:
        return StoryItemRole.INDEPENDENT_COVERAGE
    if candidate.source_role in {
        SourceRole.LAB_ANNOUNCEMENT,
        SourceRole.INSTITUTIONAL,
        SourceRole.GOVERNMENT,
        SourceRole.PRESS_RELEASE,
    }:
        return StoryItemRole.ANNOUNCEMENT
    if candidate.source_role is SourceRole.DISCOVERY:
        return StoryItemRole.DISCOVERY
    return StoryItemRole.CONTEXT


def _upsert_item(
    cursor: psycopg.Cursor[Any],
    candidate: IngestCandidate,
) -> tuple[UUID, bool]:
    existing_id: UUID | None = None
    if candidate.source_native_id:
        cursor.execute(
            """
            SELECT id
            FROM items
            WHERE source_id = %s AND source_native_id = %s;
            """,
            (candidate.source_id, candidate.source_native_id),
        )
        existing = cursor.fetchone()
        existing_id = existing[0] if existing else None

    if existing_id is None:
        cursor.execute(
            "SELECT id FROM items WHERE canonical_hash = %s;",
            (candidate.canonical_hash,),
        )
        existing = cursor.fetchone()
        existing_id = existing[0] if existing else None

    values = (
        candidate.source_id,
        candidate.source_native_id,
        candidate.url,
        candidate.canonical_url,
        candidate.canonical_hash,
        candidate.title,
        candidate.snippet,
        candidate.content_type.value,
        candidate.content_type_basis,
        candidate.content_type_note,
        candidate.published_at,
        candidate.image_url,
        candidate.doi,
        candidate.arxiv_id,
        candidate.access_class.value,
    )
    if existing_id is None:
        cursor.execute(
            """
            INSERT INTO items (
              source_id,
              source_native_id,
              url,
              canonical_url,
              canonical_hash,
              title,
              snippet,
              content_type,
              content_type_basis,
              content_type_note,
              published_at,
              image_url,
              doi,
              arxiv_id,
              access_class
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id;
            """,
            values,
        )
        inserted = cursor.fetchone()
        if inserted is None:
            raise RuntimeError("item insert returned no ID")
        return inserted[0], True

    cursor.execute(
        """
        UPDATE items SET
          source_id = %s,
          source_native_id = %s,
          url = %s,
          canonical_url = %s,
          canonical_hash = %s,
          title = %s,
          snippet = %s,
          content_type = CASE
            WHEN items.content_type_basis IN ('document', 'classifier')
            THEN items.content_type ELSE %s END,
          content_type_basis = CASE
            WHEN items.content_type_basis IN ('document', 'classifier')
            THEN items.content_type_basis ELSE %s END,
          content_type_note = CASE
            WHEN items.content_type_basis IN ('document', 'classifier')
            THEN items.content_type_note ELSE %s END,
          published_at = COALESCE(%s, published_at),
          -- A publisher that drops the image from a re-listed entry has not
          -- withdrawn it, and the same COALESCE that protects the DOI protects
          -- this: a later feed read never blanks what an earlier one found.
          image_url = COALESCE(%s, image_url),
          doi = COALESCE(%s, doi),
          arxiv_id = COALESCE(%s, arxiv_id),
          -- A feed entry only ever carries a snippet or nothing at all, so
          -- re-seeing one says nothing about the text we since fetched.
          -- Retrieval and hydration both raise this and say in as many words
          -- that it "only ever rises"; ingest was quietly lowering it again
          -- every time a publisher's window still listed the entry.
          access_class = CASE
            WHEN items.access_class IN ('abstract', 'open_full_text')
            THEN items.access_class ELSE %s END,
          updated_at = now()
        WHERE id = %s;
        """,
        (*values, existing_id),
    )
    return existing_id, False


def _paper_for_item(
    cursor: psycopg.Cursor[Any],
    candidate: IngestCandidate,
    item_id: UUID,
) -> UUID | None:
    if not candidate.doi and not candidate.arxiv_id:
        return None

    if candidate.doi and candidate.arxiv_id:
        cursor.execute(
            """
            SELECT id
            FROM papers
            WHERE lower(doi) = lower(%s)
               OR lower(arxiv_id) = lower(%s)
            ORDER BY created_at ASC
            LIMIT 1;
            """,
            (candidate.doi, candidate.arxiv_id),
        )
    elif candidate.doi:
        cursor.execute(
            """
            SELECT id
            FROM papers
            WHERE lower(doi) = lower(%s)
            ORDER BY created_at ASC
            LIMIT 1;
            """,
            (candidate.doi,),
        )
    else:
        cursor.execute(
            """
            SELECT id
            FROM papers
            WHERE lower(arxiv_id) = lower(%s)
            ORDER BY created_at ASC
            LIMIT 1;
            """,
            (candidate.arxiv_id,),
        )
    row = cursor.fetchone()
    if row:
        paper_id = cast(UUID, row[0])
        cursor.execute(
            """
            UPDATE papers SET
              doi = COALESCE(doi, %s),
              arxiv_id = COALESCE(arxiv_id, %s),
              title = CASE
                WHEN length(%s) > length(title) THEN %s
                ELSE title
              END,
              updated_at = now()
            WHERE id = %s;
            """,
            (
                candidate.doi,
                candidate.arxiv_id,
                candidate.title,
                candidate.title,
                paper_id,
            ),
        )
    else:
        cursor.execute(
            """
            INSERT INTO papers (title, doi, arxiv_id, access_class)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (
                candidate.title,
                candidate.doi,
                candidate.arxiv_id,
                candidate.access_class.value
                if candidate.access_class.value != "snippet"
                else "metadata_only",
            ),
        )
        inserted = cursor.fetchone()
        if inserted is None:
            raise RuntimeError("paper insert returned no ID")
        paper_id = cast(UUID, inserted[0])

    match_kind = "doi" if candidate.doi else "arxiv_id"
    cursor.execute(
        """
        INSERT INTO item_papers (item_id, paper_id, match_kind)
        VALUES (%s, %s, %s)
        ON CONFLICT (item_id, paper_id) DO UPDATE SET
          match_kind = EXCLUDED.match_kind,
          match_confidence = 1.0;
        """,
        (item_id, paper_id, match_kind),
    )
    return paper_id


def _attach_story(
    cursor: psycopg.Cursor[Any],
    candidate: IngestCandidate,
    item_id: UUID,
    paper_id: UUID | None,
) -> tuple[bool, bool]:
    cursor.execute(
        "SELECT story_id FROM story_items WHERE item_id = %s LIMIT 1;",
        (item_id,),
    )
    existing_membership = cursor.fetchone()
    if existing_membership:
        return False, False

    story_id: UUID | None = None
    cluster_method = "canonical_url"
    if paper_id is not None:
        cursor.execute(
            """
            SELECT si.story_id
            FROM story_items si
            JOIN item_papers ip ON ip.item_id = si.item_id
            WHERE ip.paper_id = %s
            ORDER BY si.added_at ASC
            LIMIT 1;
            """,
            (paper_id,),
        )
        existing_story = cursor.fetchone()
        if existing_story:
            story_id = existing_story[0]
            cluster_method = "paper_identifier"

    created_story = story_id is None
    if story_id is None:
        cursor.execute(
            """
            INSERT INTO stories (
              working_title,
              status,
              published_at,
              last_evidence_at
            )
            -- Draft, not published. A story arrives as evidence; it becomes
            -- a story a reader is offered once something has been written about
            -- it, which generation decides. Publishing on arrival is what made
            -- the feed a mirror of fifteen RSS headlines.
            VALUES (%s, 'draft', COALESCE(%s, now()), COALESCE(%s, now()))
            RETURNING id;
            """,
            (
                candidate.title,
                candidate.published_at,
                candidate.published_at,
            ),
        )
        story_row = cursor.fetchone()
        if story_row is None:
            raise RuntimeError("story insert returned no ID")
        story_id = story_row[0]

    cursor.execute(
        """
        INSERT INTO story_items (
          story_id,
          item_id,
          role,
          cluster_method,
          cluster_score,
          cluster_reason
        )
        VALUES (%s, %s, %s, %s, 1.0, %s);
        """,
        (
            story_id,
            item_id,
            _story_item_role(candidate).value,
            cluster_method,
            Jsonb({"identifier": candidate.doi or candidate.arxiv_id}),
        ),
    )
    cursor.execute(
        """
        UPDATE stories SET
          last_evidence_at = GREATEST(
            COALESCE(last_evidence_at, '-infinity'::timestamptz),
            COALESCE(%s, now())
          ),
          updated_at = now()
        WHERE id = %s;
        """,
        (candidate.published_at, story_id),
    )
    return created_story, True


def persist_feed_batch(
    connection: psycopg.Connection[Any],
    *,
    feed_id: UUID,
    batch: FeedBatch,
    started_at: datetime,
    finished_at: datetime,
    pipeline_run_id: UUID | None = None,
) -> PersistBatchResult:
    """Atomically persist normalized items and their evidence-only stories."""

    inserted_items = 0
    updated_items = 0
    created_stories = 0
    attached_items = 0

    with connection.transaction(), connection.cursor() as cursor:
        for candidate in batch.candidates:
            item_id, inserted = _upsert_item(cursor, candidate)
            inserted_items += int(inserted)
            updated_items += int(not inserted)
            paper_id = _paper_for_item(cursor, candidate, item_id)
            story_created, item_attached = _attach_story(
                cursor,
                candidate,
                item_id,
                paper_id,
            )
            created_stories += int(story_created)
            attached_items += int(item_attached)

        cursor.execute(
            """
            UPDATE source_feeds SET
              last_fetched_at = %s,
              last_status = %s,
              etag = %s,
              last_modified = %s,
              error_streak = 0,
              next_fetch_at = %s + make_interval(mins => fetch_interval_minutes),
              updated_at = now()
            WHERE id = %s;
            """,
            (
                finished_at,
                batch.status.value,
                batch.etag,
                batch.last_modified,
                finished_at,
                feed_id,
            ),
        )
        cursor.execute(
            """
            INSERT INTO feed_fetches (
              source_feed_id,
              pipeline_run_id,
              status,
              http_status,
              items_seen,
              started_at,
              finished_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s);
            """,
            (
                feed_id,
                pipeline_run_id,
                batch.status.value,
                batch.http_status,
                len(batch.candidates) + batch.skipped_entries,
                started_at,
                finished_at,
            ),
        )

    return PersistBatchResult(
        inserted_items=inserted_items,
        updated_items=updated_items,
        created_stories=created_stories,
        attached_items=attached_items,
    )


def record_feed_failure(
    connection: psycopg.Connection[Any],
    *,
    feed_id: UUID,
    started_at: datetime,
    finished_at: datetime,
    error: str,
    pipeline_run_id: UUID | None = None,
) -> None:
    """Record a bounded error and schedule exponential retry."""

    summary = error[:1000]
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE source_feeds SET
              last_fetched_at = %s,
              last_status = 'failed',
              error_streak = error_streak + 1,
              next_fetch_at = %s + make_interval(
                mins => LEAST(
                  fetch_interval_minutes
                    * CAST(power(2, LEAST(error_streak, 5)) AS INTEGER),
                  1440
                )
              ),
              updated_at = now()
            WHERE id = %s;
            """,
            (finished_at, finished_at, feed_id),
        )
        cursor.execute(
            """
            INSERT INTO feed_fetches (
              source_feed_id,
              pipeline_run_id,
              status,
              items_seen,
              error_message,
              started_at,
              finished_at
            )
            VALUES (%s, %s, 'failed', 0, %s, %s, %s);
            """,
            (
                feed_id,
                pipeline_run_id,
                summary,
                started_at,
                finished_at,
            ),
        )
