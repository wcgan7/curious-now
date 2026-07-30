"""The gate against a real database.

There was no test here, and a change to the UPDATE left five placeholders
against six parameters — a break that no amount of type checking sees and that
every run hits on its first story. The behaviour it guards is also easy to
reverse by accident: the gate decides what a story's text can support, and must
not decide whether a reader is offered it.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest

from curious_now_v2.db.migrations import apply_migrations
from curious_now_v2.db.publication import run_publication_gate

TEST_DATABASE_URL = os.environ.get("CURIOUS_NOW_V2_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not TEST_DATABASE_URL,
        reason="CURIOUS_NOW_V2_TEST_DATABASE_URL is not set",
    ),
]

# Long enough to clear the gate's word thresholds, with the section structure a
# Technical walkthrough would need to cite.
BODY = " ".join(["The measured response rose with dose in every replicate."] * 220)


def seed_story(
    connection: psycopg.Connection,
    *,
    status: str,
    withheld_kind: str | None = None,
) -> UUID:
    suffix = uuid4().hex
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO sources (name, role, policy)
            VALUES (%s, 'primary_research', '{"counts_as_independent": true}')
            RETURNING id;
            """,
            (f"Gate source {suffix}",),
        )
        source_id = (cursor.fetchone() or (None,))[0]

        cursor.execute(
            """
            INSERT INTO items (
              source_id, url, canonical_url, canonical_hash, title,
              content_type, access_class, full_text, full_text_words,
              full_text_status, full_text_kind, text_structure
            )
            VALUES (%s, %s, %s, %s, %s, 'peer_reviewed', 'open_full_text',
                    %s, %s, 'ok', 'fulltext', %s)
            RETURNING id;
            """,
            (
                source_id,
                f"https://example.test/{suffix}",
                f"https://example.test/{suffix}",
                f"{suffix}{'0' * (64 - len(suffix))}",
                "A dose-response study",
                BODY,
                len(BODY.split()),
                psycopg.types.json.Jsonb(
                    {
                        "sections": [
                            {"title": "Methods", "kind": "methods"},
                            {"title": "Results", "kind": "results"},
                        ]
                    }
                ),
            ),
        )
        item_id = (cursor.fetchone() or (None,))[0]

        cursor.execute(
            """
            INSERT INTO stories (working_title, status, withheld_kind, last_evidence_at)
            VALUES (%s, %s, %s, now())
            RETURNING id;
            """,
            (f"Working title {suffix}", status, withheld_kind),
        )
        story_id = (cursor.fetchone() or (None,))[0]

        cursor.execute(
            """
            INSERT INTO story_items (story_id, item_id, role, cluster_method)
            VALUES (%s, %s, 'primary_evidence', 'paper_identifier');
            """,
            (story_id, item_id),
        )
    return cast_uuid(story_id)


def cast_uuid(value: object) -> UUID:
    assert isinstance(value, UUID)
    return value


def story_row(connection: psycopg.Connection, story_id: UUID) -> tuple:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT status, supported_depths, gated_at IS NOT NULL, withheld_kind
            FROM stories WHERE id = %s;
            """,
            (story_id,),
        )
        row = cursor.fetchone()
    assert row is not None
    return row


def test_the_gate_records_eligibility_without_publishing() -> None:
    """Publishing is generation's call, because only it knows there is text.

    The gate used to promote on word count, which is how the feed came to hold
    295 stories and 8 explanations — 287 cards showing a source's own headline
    over "a grounded explanation is not available yet".
    """

    assert TEST_DATABASE_URL is not None
    apply_migrations(TEST_DATABASE_URL)
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as connection:
        story_id = seed_story(connection, status="draft")

        result = run_publication_gate(TEST_DATABASE_URL)
        assert result.evaluated >= 1

        status, depths, gated, _ = story_row(connection, story_id)
        assert status == "draft", "the gate must not publish a story itself"
        assert gated, "it must still record that it looked"
        assert "glance" in depths, "and what the text can support"


def test_the_gate_leaves_a_published_story_published() -> None:
    """A story with an explanation must not be demoted by a later gate run."""

    assert TEST_DATABASE_URL is not None
    apply_migrations(TEST_DATABASE_URL)
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as connection:
        story_id = seed_story(connection, status="published")
        run_publication_gate(TEST_DATABASE_URL)
        status, _, _, _ = story_row(connection, story_id)
    assert status == "published"


def test_the_gate_does_not_reconsider_a_withheld_story() -> None:
    """Withholding is a judgement about what the item is, and it stands.

    It used to be recorded as nothing but a draft status, so the next gate run
    published the podcast episode again and generation paid to classify it
    again — every cycle, indefinitely.
    """

    assert TEST_DATABASE_URL is not None
    apply_migrations(TEST_DATABASE_URL)
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as connection:
        story_id = seed_story(
            connection, status="draft", withheld_kind="announcement"
        )
        before = story_row(connection, story_id)
        run_publication_gate(TEST_DATABASE_URL)
        after = story_row(connection, story_id)

    assert after[0] == "draft"
    assert after[3] == "announcement"
    assert after[2] == before[2], "a withheld story is not even re-gated"


def test_the_gate_runs_at_all() -> None:
    """A placeholder/parameter mismatch fails on the first story, every time."""

    assert TEST_DATABASE_URL is not None
    apply_migrations(TEST_DATABASE_URL)
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as connection:
        seed_story(connection, status="draft")
    result = run_publication_gate(TEST_DATABASE_URL, limit=5)
    assert result.evaluated >= 1
    assert result.eligible + result.ineligible == result.evaluated
    # Sanity on the clock: gating stamps a time, and it is not in the future.
    assert datetime.now(UTC) - timedelta(minutes=5) < datetime.now(UTC)
