from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

from curious_now_v2.core.enums import ContentType, SourceRole
from curious_now_v2.core.source_registry import (
    FeedSpec,
    SourcePolicy,
    SourceRegistry,
    SourceSpec,
)
from curious_now_v2.db.ingestion import (
    list_due_feeds,
    persist_feed_batch,
    sync_source_registry,
)
from curious_now_v2.db.migrations import apply_migrations
from curious_now_v2.pipeline.feed_reader import FeedBatch, FeedReadStatus
from curious_now_v2.pipeline.ingest import RawFeedEntry, normalize_entry

TEST_DATABASE_URL = os.environ.get("CURIOUS_NOW_V2_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not TEST_DATABASE_URL,
        reason="CURIOUS_NOW_V2_TEST_DATABASE_URL is not set",
    ),
]


def test_exact_paper_ids_cluster_two_items_into_one_evidence_only_story() -> None:
    assert TEST_DATABASE_URL is not None
    apply_migrations(TEST_DATABASE_URL)

    suffix = uuid4().hex
    feed = FeedSpec(
        url=f"https://example.test/{suffix}/feed.xml",
        default_content_type=ContentType.PREPRINT,
    )
    source = SourceSpec(
        name=f"Integration preprints {suffix}",
        homepage_url="https://example.test/",
        role=SourceRole.PRIMARY_RESEARCH,
        feeds=(feed,),
        policy=SourcePolicy(
            counts_as_independent=False,
            allow_full_text_extraction=True,
        ),
    )
    registry = SourceRegistry(version=1, sources=(source,))
    doi = f"10.5555/{suffix}"

    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as connection:
        sync_source_registry(connection, registry)
        now = datetime.now(UTC)
        due_feeds = list_due_feeds(connection, now=now, limit=100)
        due = next(value for value in due_feeds if value.feed.url == feed.url)

        entries = (
            RawFeedEntry(
                source_id=due.source_id,
                source_name=source.name,
                source_role=source.role,
                source_native_id=f"{suffix}-paper",
                title=f"A shared result doi:{doi}",
                url=f"https://example.test/{suffix}/paper",
                default_content_type=ContentType.PREPRINT,
            ),
            RawFeedEntry(
                source_id=due.source_id,
                source_name=source.name,
                source_role=source.role,
                source_native_id=f"{suffix}-coverage",
                title=f"More detail on doi:{doi}",
                url=f"https://example.test/{suffix}/coverage",
                default_content_type=ContentType.PREPRINT,
            ),
        )
        batch = FeedBatch(
            source_id=due.source_id,
            feed_url=feed.url,
            status=FeedReadStatus.SUCCEEDED,
            http_status=200,
            etag='"integration"',
            last_modified=None,
            candidates=tuple(normalize_entry(entry) for entry in entries),
            skipped_entries=0,
        )

        first = persist_feed_batch(
            connection,
            feed_id=due.feed_id,
            batch=batch,
            started_at=now,
            finished_at=now,
        )
        second = persist_feed_batch(
            connection,
            feed_id=due.feed_id,
            batch=batch,
            started_at=now,
            finished_at=now,
        )

        assert first.inserted_items == 2
        assert first.created_stories == 1
        assert first.attached_items == 2
        assert second.updated_items == 2
        assert second.created_stories == 0
        assert second.attached_items == 0

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(DISTINCT si.story_id), count(DISTINCT si.item_id)
                FROM story_items si
                JOIN items i ON i.id = si.item_id
                WHERE i.source_id = %s;
                """,
                (due.source_id,),
            )
            counts = cursor.fetchone()

    assert counts == (1, 2)
