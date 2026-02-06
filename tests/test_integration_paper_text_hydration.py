from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import psycopg

from curious_now.ai.llm_adapter import MockAdapter
from curious_now.ai_generation import generate_deep_dives_for_clusters
from curious_now.paper_text_hydration import HydratePaperTextResult, hydrate_paper_text


def test_hydrate_paper_text_updates_item(db_conn: psycopg.Connection[Any], monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source_id = uuid4()
    item_id = uuid4()
    now = datetime.now(timezone.utc)

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources(id, name, source_type, active)
            VALUES (%s, %s, %s, %s);
            """,
            (source_id, "arXiv", "preprint_server", True),
        )
        cur.execute(
            """
            INSERT INTO items(
              id, source_id, url, canonical_url, title, fetched_at, snippet,
              content_type, language, title_hash, canonical_hash, arxiv_id, full_text_status
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'en',%s,%s,%s,%s);
            """,
            (
                item_id,
                source_id,
                "https://arxiv.org/abs/1234.56789",
                "https://arxiv.org/abs/1234.56789",
                "Test paper",
                now,
                "short snippet",
                "preprint",
                "th",
                "ch",
                "1234.56789",
                "pending",
            ),
        )

    monkeypatch.setattr(
        "curious_now.paper_text_hydration._extract_item_text",
        lambda _item: ("Hydrated abstract text from provider", "ok", "mock"),
    )

    result = hydrate_paper_text(db_conn, limit=10, item_ids=[item_id], now_utc=now)
    assert result.items_scanned == 1
    assert result.items_hydrated == 1
    assert result.items_failed == 0

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT full_text, full_text_status, full_text_source FROM items WHERE id = %s;",
            (item_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row["full_text"] == "Hydrated abstract text from provider"
    assert row["full_text_status"] == "ok"
    assert row["full_text_source"] == "mock"


def test_generate_deep_dives_skips_when_paper_text_missing(
    db_conn: psycopg.Connection[Any], monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    source_id = uuid4()
    item_id = uuid4()
    cluster_id = uuid4()
    now = datetime.now(timezone.utc)

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources(id, name, source_type, active)
            VALUES (%s, %s, %s, %s);
            """,
            (source_id, "Test Journal", "journal", True),
        )
        cur.execute(
            """
            INSERT INTO items(
              id, source_id, url, canonical_url, title, fetched_at, snippet,
              content_type, language, title_hash, canonical_hash, doi, full_text_status
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'en',%s,%s,%s,%s);
            """,
            (
                item_id,
                source_id,
                "https://example.org/paper",
                "https://example.org/paper",
                "Paper without hydrated text",
                now,
                "snippet only",
                "peer_reviewed",
                "th2",
                "ch2",
                "10.1234/example",
                "pending",
            ),
        )
        cur.execute(
            """
            INSERT INTO story_clusters(id, status, canonical_title, takeaway)
            VALUES (%s, 'active', %s, %s);
            """,
            (cluster_id, "Paper cluster", "Existing takeaway"),
        )
        cur.execute(
            """
            INSERT INTO cluster_items(cluster_id, item_id, role)
            VALUES (%s, %s, 'primary');
            """,
            (cluster_id, item_id),
        )

    monkeypatch.setattr(
        "curious_now.ai_generation.hydrate_paper_text",
        lambda conn, limit, item_ids: HydratePaperTextResult(
            items_scanned=len(item_ids),
            items_hydrated=0,
            items_failed=len(item_ids),
            items_skipped=0,
        ),
    )

    adapter = MockAdapter(responses={"Technical Deep Dive": "## Overview\nShould not be used"})
    result = generate_deep_dives_for_clusters(db_conn, limit=10, adapter=adapter)
    assert result.clusters_processed == 1
    assert result.clusters_succeeded == 0
    assert result.clusters_failed == 0
    assert result.clusters_skipped == 1
