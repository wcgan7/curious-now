from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import psycopg

from curious_now.ai.llm_adapter import MockAdapter
from curious_now.ai_generation import generate_deep_dives_for_clusters
from curious_now.paper_text_hydration import HydratePaperTextResult, hydrate_paper_text


def _row_get(row: Any, key: str, idx: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[idx]


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
        lambda _item: ("Hydrated abstract text from provider", "ok", "mock", None, None),
    )

    result = hydrate_paper_text(db_conn, limit=10, item_ids=[item_id], now_utc=now)
    assert result.items_scanned == 1
    assert result.items_hydrated == 1
    assert result.items_failed == 0

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT full_text, full_text_status, full_text_source, full_text_kind, full_text_license
            FROM items
            WHERE id = %s;
            """,
            (item_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert _row_get(row, "full_text", 0) == "Hydrated abstract text from provider"
    assert _row_get(row, "full_text_status", 1) == "ok"
    assert _row_get(row, "full_text_source", 2) == "mock"
    assert _row_get(row, "full_text_kind", 3) is None
    assert _row_get(row, "full_text_license", 4) is None


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
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT deep_dive_skip_reason FROM story_clusters WHERE id = %s;",
            (cluster_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert _row_get(row, "deep_dive_skip_reason", 0) == "no_fulltext"


def test_generate_deep_dives_skips_abstract_only_but_generates_intuition(
    db_conn: psycopg.Connection[Any],
) -> None:
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
            (source_id, "arXiv", "preprint_server", True),
        )
        cur.execute(
            """
            INSERT INTO items(
              id, source_id, url, canonical_url, title, fetched_at, snippet,
              content_type, language, title_hash, canonical_hash, arxiv_id,
              full_text, full_text_status, full_text_source
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'en',%s,%s,%s,%s,%s,%s);
            """,
            (
                item_id,
                source_id,
                "https://arxiv.org/abs/1234.56789",
                "https://arxiv.org/abs/1234.56789",
                "Abstract-only paper",
                now,
                "snippet only",
                "preprint",
                "th3",
                "ch3",
                "1234.56789",
                "This is the abstract content from arXiv API.",
                "ok",
                "arxiv_api",
            ),
        )
        cur.execute(
            """
            INSERT INTO story_clusters(id, status, canonical_title, takeaway)
            VALUES (%s, 'active', %s, %s);
            """,
            (cluster_id, "Abstract-only cluster", "Existing takeaway"),
        )
        cur.execute(
            """
            INSERT INTO cluster_items(cluster_id, item_id, role)
            VALUES (%s, %s, 'primary');
            """,
            (cluster_id, item_id),
        )

    adapter = MockAdapter(
        responses={
            "Abstract sources": (
                "This is based on abstracts only and explains the main idea plainly."
            )
        }
    )
    result = generate_deep_dives_for_clusters(db_conn, limit=10, adapter=adapter)
    assert result.clusters_processed == 1
    assert result.clusters_succeeded == 0
    assert result.clusters_failed == 0
    assert result.clusters_skipped == 1

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT summary_deep_dive, summary_intuition, deep_dive_skip_reason
            FROM story_clusters
            WHERE id = %s;
            """,
            (cluster_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert _row_get(row, "summary_deep_dive", 0) is None
    intuition = _row_get(row, "summary_intuition", 1)
    assert isinstance(intuition, str) and intuition.strip()
    assert _row_get(row, "deep_dive_skip_reason", 2) == "abstract_only"
