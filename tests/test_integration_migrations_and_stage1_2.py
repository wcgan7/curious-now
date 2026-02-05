from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from curious_now.migrations import migrate


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.mark.integration
def test_migrate_idempotent(db_conn: psycopg.Connection) -> None:
    migrations_dir = Path(__file__).resolve().parents[1] / "design_docs" / "migrations"
    applied = migrate(db_conn, migrations_dir=migrations_dir)
    assert applied == []


@pytest.mark.integration
def test_migrate_idempotent_with_dict_rows(database_url: str) -> None:
    migrations_dir = Path(__file__).resolve().parents[1] / "design_docs" / "migrations"
    conn = psycopg.connect(database_url, row_factory=dict_row)
    conn.autocommit = True
    try:
        applied = migrate(conn, migrations_dir=migrations_dir)
        assert applied == []
    finally:
        conn.close()


@pytest.mark.integration
def test_stage1_admin_source_pack_import_and_sources(client) -> None:  # type: ignore[no-untyped-def]
    os.environ["CN_ADMIN_TOKEN"] = "test-admin-token"

    resp = client.post(
        "/v1/admin/source_pack/import",
        headers={"X-Admin-Token": "test-admin-token"},
        json={
            "sources": [
                {
                    "name": "Example News",
                    "homepage_url": "https://example.com",
                    "source_type": "journalism",
                    "reliability_tier": "tier2",
                    "terms_notes": "test",
                    "active": True,
                    "feeds": [
                        {
                            "feed_url": "https://example.com/rss.xml",
                            "feed_type": "rss",
                            "fetch_interval_minutes": 10,
                        }
                    ],
                }
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sources_upserted"] == 1
    assert body["feeds_upserted"] == 1

    resp = client.get("/v1/sources")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["sources"]) == 1
    assert data["sources"][0]["source"]["name"] == "Example News"
    assert len(data["sources"][0]["feeds"]) == 1


@pytest.mark.integration
def test_stage1_items_feed(client, db_conn: psycopg.Connection) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(timezone.utc)
    source_id = uuid4()
    item_id = uuid4()
    url = "https://example.com/story"
    canonical_url = "https://example.com/story"

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources(id, name, source_type, active)
            VALUES (%s, %s, %s, %s);
            """,
            (source_id, "Example News", "journalism", True),
        )
        cur.execute(
            """
            INSERT INTO items(
              id, source_id, url, canonical_url, title, published_at, fetched_at,
              content_type, language, title_hash, canonical_hash
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (
                item_id,
                source_id,
                url,
                canonical_url,
                "A test story",
                now,
                now,
                "news",
                "en",
                _sha256_hex("A test story"),
                _sha256_hex(canonical_url),
            ),
        )

    resp = client.get("/v1/items/feed?page=1&page_size=10")
    assert resp.status_code == 200, resp.text
    items = resp.json()["results"]
    assert len(items) == 1
    assert items[0]["item_id"] == str(item_id)
    assert items[0]["source"]["name"] == "Example News"


@pytest.mark.integration
def test_stage2_feed_cluster_topic_search_and_redirect(client, db_conn: psycopg.Connection) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(timezone.utc)
    source_id = uuid4()
    item_id = uuid4()
    cluster_id = uuid4()
    topic_id = uuid4()

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sources(id, name, source_type, active) VALUES (%s,%s,%s,%s);",
            (source_id, "Example News", "journalism", True),
        )
        cur.execute(
            """
            INSERT INTO items(
              id, source_id, url, canonical_url, title, published_at, fetched_at,
              content_type, language, title_hash, canonical_hash
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (
                item_id,
                source_id,
                "https://example.com/story2",
                "https://example.com/story2",
                "AlphaBeta research",
                now,
                now,
                "preprint",
                "en",
                _sha256_hex("AlphaBeta research"),
                _sha256_hex("https://example.com/story2"),
            ),
        )
        cur.execute(
            """
            INSERT INTO story_clusters(
              id, status, canonical_title, representative_item_id,
              distinct_source_count, distinct_source_type_count, item_count,
              velocity_6h, velocity_24h, trending_score, recency_score
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (
                cluster_id,
                "active",
                "AlphaBeta cluster",
                item_id,
                1,
                1,
                1,
                1,
                1,
                10.0,
                1.0,
            ),
        )
        cur.execute(
            "INSERT INTO cluster_items(cluster_id, item_id, role) VALUES (%s,%s,%s);",
            (cluster_id, item_id, "primary"),
        )
        cur.execute(
            "INSERT INTO topics(id, name, description_short) VALUES (%s,%s,%s);",
            (topic_id, "AI", "Artificial intelligence"),
        )
        cur.execute(
            "INSERT INTO cluster_topics(cluster_id, topic_id, score) VALUES (%s,%s,%s);",
            (cluster_id, topic_id, 0.9),
        )
        cur.execute(
            "INSERT INTO cluster_search_docs(cluster_id, search_text) VALUES (%s,%s);",
            (cluster_id, "AlphaBeta research AI"),
        )

    resp = client.get("/v1/feed?tab=latest&page=1&page_size=10")
    assert resp.status_code == 200, resp.text
    feed = resp.json()
    assert feed["results"][0]["cluster_id"] == str(cluster_id)
    assert feed["results"][0]["top_topics"][0]["topic_id"] == str(topic_id)

    resp = client.get(f"/v1/clusters/{cluster_id}")
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["cluster_id"] == str(cluster_id)
    assert "preprint" in detail["evidence"]
    assert detail["evidence"]["preprint"][0]["item_id"] == str(item_id)

    resp = client.get("/v1/topics")
    assert resp.status_code == 200, resp.text
    assert resp.json()["topics"][0]["topic_id"] == str(topic_id)

    resp = client.get(f"/v1/topics/{topic_id}")
    assert resp.status_code == 200, resp.text
    topic_detail = resp.json()
    assert topic_detail["topic"]["topic_id"] == str(topic_id)
    assert topic_detail["latest_clusters"][0]["cluster_id"] == str(cluster_id)

    resp = client.get("/v1/search?q=AlphaBeta")
    assert resp.status_code == 200, resp.text
    search = resp.json()
    assert search["clusters"][0]["cluster_id"] == str(cluster_id)

    # Redirect behavior
    from_cluster = uuid4()
    to_cluster = uuid4()
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO story_clusters(
              id, status, canonical_title,
              distinct_source_count, distinct_source_type_count, item_count,
              velocity_6h, velocity_24h, trending_score, recency_score
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (from_cluster, "merged", "Old cluster", 0, 0, 0, 0, 0, 0.0, 0.0),
        )
        cur.execute(
            """
            INSERT INTO story_clusters(
              id, status, canonical_title,
              distinct_source_count, distinct_source_type_count, item_count,
              velocity_6h, velocity_24h, trending_score, recency_score
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (to_cluster, "active", "New cluster", 0, 0, 0, 0, 0, 0.0, 0.0),
        )
        cur.execute(
            "INSERT INTO cluster_redirects(from_cluster_id, to_cluster_id) VALUES (%s,%s);",
            (from_cluster, to_cluster),
        )

    resp = client.get(f"/v1/clusters/{from_cluster}", follow_redirects=False)
    assert resp.status_code == 301, resp.text
    assert resp.json()["redirect_to_cluster_id"] == str(to_cluster)


@pytest.mark.integration
def test_stage3_glossary_and_cluster_glossary_entries(client, db_conn: psycopg.Connection) -> None:  # type: ignore[no-untyped-def]
    cluster_id = uuid4()
    source_id = uuid4()
    item_id = uuid4()
    glossary_id = uuid4()

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sources(id, name, source_type, active) VALUES (%s,%s,%s,%s);",
            (source_id, "Example News", "journalism", True),
        )
        cur.execute(
            """
            INSERT INTO items(
              id, source_id, url, canonical_url, title, fetched_at,
              content_type, language, title_hash, canonical_hash
            ) VALUES (%s,%s,%s,%s,%s,now(),%s,%s,%s,%s);
            """,
            (
                item_id,
                source_id,
                "https://example.com/story3",
                "https://example.com/story3",
                "Transformer paper",
                "peer_reviewed",
                "en",
                _sha256_hex("Transformer paper"),
                _sha256_hex("https://example.com/story3"),
            ),
        )
        cur.execute(
            """
            INSERT INTO story_clusters(
              id, status, canonical_title, representative_item_id,
              distinct_source_count, distinct_source_type_count, item_count,
              velocity_6h, velocity_24h, trending_score, recency_score
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (cluster_id, "active", "Transformers", item_id, 1, 1, 1, 0, 0, 0.0, 0.0),
        )
        cur.execute(
            "INSERT INTO cluster_items(cluster_id, item_id, role) VALUES (%s,%s,%s);",
            (cluster_id, item_id, "primary"),
        )
        cur.execute(
            """
            INSERT INTO glossary_entries(id, term, definition_short, definition_long, aliases)
            VALUES (%s,%s,%s,%s,%s::jsonb);
            """,
            (
                glossary_id,
                "Transformer",
                "A neural network architecture using attention.",
                "Longer definition.",
                '["transformer"]',
            ),
        )
        cur.execute(
            """
            INSERT INTO cluster_glossary_links(cluster_id, glossary_entry_id, score)
            VALUES (%s,%s,%s);
            """,
            (cluster_id, glossary_id, 1.0),
        )

    resp = client.get("/v1/glossary?term=Transformer")
    assert resp.status_code == 200, resp.text
    assert resp.json()["entry"]["term"] == "Transformer"

    resp = client.get(f"/v1/clusters/{cluster_id}")
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["glossary_entries"][0]["term"] == "Transformer"


@pytest.mark.integration
def test_stage4_updates_and_lineage(client, db_conn: psycopg.Connection) -> None:  # type: ignore[no-untyped-def]
    cluster_id = uuid4()
    topic_id = uuid4()
    evidence_item_id = uuid4()
    node_a = uuid4()
    node_b = uuid4()

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO story_clusters(
              id, status, canonical_title,
              distinct_source_count, distinct_source_type_count, item_count,
              velocity_6h, velocity_24h, trending_score, recency_score
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (cluster_id, "active", "Update test", 0, 0, 0, 0, 0, 0.0, 0.0),
        )
        cur.execute(
            """
            INSERT INTO update_log_entries(
              cluster_id, change_type, summary, diff, supporting_item_ids
            )
            VALUES (%s,%s,%s,%s::jsonb,%s::jsonb);
            """,
            (
                cluster_id,
                "refinement",
                "Updated the summary based on new evidence.",
                '{"previously":["a"],"now":["b"],"because":["c"]}',
                f'["{evidence_item_id}"]',
            ),
        )

        cur.execute(
            """
            INSERT INTO lineage_nodes(id, node_type, title, external_url, topic_ids)
            VALUES (%s,%s,%s,%s,%s::jsonb);
            """,
            (node_a, "model", "BERT", "https://example.com/bert", f'["{topic_id}"]'),
        )
        cur.execute(
            """
            INSERT INTO lineage_nodes(id, node_type, title, external_url, topic_ids)
            VALUES (%s,%s,%s,%s,%s::jsonb);
            """,
            (node_b, "model", "ALBERT", "https://example.com/albert", f'["{topic_id}"]'),
        )
        cur.execute(
            """
            INSERT INTO lineage_edges(
              from_node_id, to_node_id, relation_type, evidence_item_ids, notes_short
            )
            VALUES (%s,%s,%s,%s::jsonb,%s);
            """,
            (node_a, node_b, "compresses", f'["{evidence_item_id}"]', "Parameter sharing"),
        )

    resp = client.get(f"/v1/clusters/{cluster_id}/updates")
    assert resp.status_code == 200, resp.text
    updates = resp.json()["updates"]
    assert updates[0]["change_type"] == "refinement"

    resp = client.get(f"/v1/topics/{topic_id}/lineage")
    assert resp.status_code == 200, resp.text
    lineage = resp.json()
    assert lineage["topic_id"] == str(topic_id)
    assert len(lineage["nodes"]) == 2
    assert len(lineage["edges"]) == 1
