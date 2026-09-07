"""Database regressions for the generation runner's operational scope."""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from curious_now_v2.db.generation import (
    list_stories_needing_presentations,
    run_generation,
)
from curious_now_v2.db.migrations import apply_migrations

TEST_DATABASE_URL = os.environ.get("CURIOUS_NOW_V2_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not TEST_DATABASE_URL,
        reason="CURIOUS_NOW_V2_TEST_DATABASE_URL is not set",
    ),
]


def test_targeted_generation_does_not_reopen_unrelated_stories() -> None:
    """An ID filter must constrain maintenance as well as model work."""

    assert TEST_DATABASE_URL is not None
    apply_migrations(TEST_DATABASE_URL)
    suffix = uuid4().hex
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO stories (
                  working_title, status, withheld_kind, withheld_by,
                  publication_reasons, last_evidence_at
                )
                VALUES (%s, 'draft', 'announcement', 'packet-old',
                        '["older decision"]', now())
                RETURNING id;
                """,
                (f"Unrelated withheld story {suffix}",),
            )
            unrelated_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO stories (working_title, status, last_evidence_at)
                VALUES (%s, 'draft', now()) RETURNING id;
                """,
                (f"Requested story {suffix}",),
            )
            requested_id = cursor.fetchone()[0]

        result = run_generation(
            TEST_DATABASE_URL,
            limit=1,
            story_ids=[requested_id],
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT withheld_kind, withheld_by, publication_reasons
                FROM stories WHERE id = %s;
                """,
                (unrelated_id,),
            )
            withheld_kind, withheld_by, reasons = cursor.fetchone()

    assert result.attempted == 0
    assert withheld_kind == "announcement"
    assert withheld_by == "packet-old"
    assert reasons == ["older decision"]


def test_blocked_feed_item_is_not_selected_for_generation() -> None:
    """An exclusion keeps its stored body but must leave the model queue."""

    assert TEST_DATABASE_URL is not None
    apply_migrations(TEST_DATABASE_URL)
    suffix = uuid4().hex
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sources (name, role, policy)
                VALUES (%s, 'journalism', '{"counts_as_independent": true}')
                RETURNING id;
                """,
                (f"Blocked generation source {suffix}",),
            )
            source_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO items (
                  source_id, url, canonical_url, canonical_hash, title,
                  content_type, access_class, full_text, full_text_words,
                  full_text_status, full_text_kind
                )
                VALUES (%s, %s, %s, %s, 'Excluded format', 'news',
                        'open_full_text', %s, 600, 'blocked', 'fulltext')
                RETURNING id;
                """,
                (
                    source_id,
                    f"https://example.test/{suffix}",
                    f"https://example.test/{suffix}",
                    f"{suffix}{'0' * (64 - len(suffix))}",
                    "Readable text retained for audit. " * 100,
                ),
            )
            item_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO stories (
                  working_title, status, supported_depths, last_evidence_at
                )
                VALUES (%s, 'draft', ARRAY['glance'], now()) RETURNING id;
                """,
                (f"Blocked generation story {suffix}",),
            )
            story_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO story_items (story_id, item_id, role, cluster_method)
                VALUES (%s, %s, 'independent_coverage', 'singleton');
                """,
                (story_id, item_id),
            )

        pending = list_stories_needing_presentations(
            connection,
            limit=10,
            story_ids=[story_id],
        )

    assert pending == ()


def test_presentation_queue_can_target_one_source() -> None:
    assert TEST_DATABASE_URL is not None
    apply_migrations(TEST_DATABASE_URL)
    suffix = uuid4().hex
    target_name = f"Target generation source {suffix}"
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as connection:
        story_ids = []
        for source_name in (target_name, f"Other generation source {suffix}"):
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sources (name, role, policy)
                    VALUES (%s, 'journalism', '{"counts_as_independent": true}')
                    RETURNING id;
                    """,
                    (source_name,),
                )
                source_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO items (
                      source_id, url, canonical_url, canonical_hash, title,
                      content_type, access_class, full_text, full_text_words,
                      full_text_status, full_text_kind
                    )
                    VALUES (%s, %s, %s, %s, 'A reported result', 'news',
                            'open_full_text', %s, 600, 'ok', 'fulltext')
                    RETURNING id;
                    """,
                    (
                        source_id,
                        f"https://example.test/{uuid4().hex}",
                        f"https://example.test/{uuid4().hex}",
                        uuid4().hex * 2,
                        "A reported scientific result. " * 150,
                    ),
                )
                item_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO stories (
                      working_title, status, supported_depths, last_evidence_at
                    )
                    VALUES (%s, 'draft', ARRAY['glance'], now()) RETURNING id;
                    """,
                    (f"Generation queue story {uuid4().hex}",),
                )
                story_id = cursor.fetchone()[0]
                story_ids.append(story_id)
                cursor.execute(
                    """
                    INSERT INTO story_items (story_id, item_id, role, cluster_method)
                    VALUES (%s, %s, 'independent_coverage', 'singleton');
                    """,
                    (story_id, item_id),
                )

        pending = list_stories_needing_presentations(
            connection,
            limit=10,
            story_ids=story_ids,
            source=target_name,
        )

    assert len(pending) == 1
    assert pending[0].source_name == target_name
