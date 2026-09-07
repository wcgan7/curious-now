from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
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
        max_entries=7,
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
        assert due.feed.max_entries == 7

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


def test_re_ingesting_an_entry_does_not_undo_what_retrieval_established() -> None:
    """A feed entry says nothing about text we have since fetched.

    Feed candidates only ever carry a snippet or nothing at all, and publishers
    keep entries in their window for days. So every re-poll used to knock an
    item's access class back down to 'snippet', discarding the 'abstract' or
    'open_full_text' that retrieval wrote after actually reading the document.
    Retrieval and hydration both say in as many words that this value "only
    ever rises"; ingest was the one place quietly lowering it.
    """

    now = datetime.now(UTC)
    suffix = uuid4().hex
    feed = FeedSpec(
        url=f"https://example.test/{suffix}.xml",
        default_content_type=ContentType.PEER_REVIEWED,
    )
    registry = SourceRegistry(
        version=1,
        sources=(
            SourceSpec(
                name=f"Monotone Source {suffix}",
                role=SourceRole.PRIMARY_RESEARCH,
                feeds=(feed,),
                policy=SourcePolicy(counts_as_independent=True),
            ),
        )
    )

    assert TEST_DATABASE_URL is not None
    apply_migrations(TEST_DATABASE_URL)
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as connection:
        sync_source_registry(connection, registry)
        # sync stamps next_fetch_at with the database's now(), which is later
        # than the timestamp captured above.
        due = next(
            candidate
            for candidate in list_due_feeds(
                connection, now=now + timedelta(minutes=1), limit=500
            )
            if candidate.feed.url == feed.url
        )

        entry = RawFeedEntry(
            source_id=due.source_id,
            source_name=due.source.name,
            source_role=due.source.role,
            source_native_id="monotone-1",
            title="A paper with a summary in its feed entry",
            url="https://example.test/paper/monotone-1",
            summary="A short teaser from the feed.",
            default_content_type=ContentType.PEER_REVIEWED,
        )
        batch = FeedBatch(
            source_id=due.source_id,
            feed_url=feed.url,
            status=FeedReadStatus.SUCCEEDED,
            http_status=200,
            etag=None,
            last_modified=None,
            candidates=(normalize_entry(entry),),
            skipped_entries=0,
        )
        persist_feed_batch(
            connection, feed_id=due.feed_id, batch=batch,
            started_at=now, finished_at=now,
        )

        with connection.cursor() as cursor:
            # Stand in for retrieval having read the document.
            cursor.execute(
                """
                UPDATE items SET access_class = 'open_full_text'
                WHERE source_native_id = 'monotone-1' AND source_id = %s;
                """,
                (due.source_id,),
            )

        # The publisher's window still lists the entry on the next poll.
        persist_feed_batch(
            connection, feed_id=due.feed_id, batch=batch,
            started_at=now, finished_at=now,
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT access_class FROM items
                WHERE source_native_id = 'monotone-1' AND source_id = %s;
                """,
                (due.source_id,),
            )
            row = cursor.fetchone()

    assert row == ("open_full_text",)
