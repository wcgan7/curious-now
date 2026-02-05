from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.mark.integration
def test_stage8_feedback_topics_and_cluster_ops(client, db_conn: psycopg.Connection) -> None:  # type: ignore[no-untyped-def]
    os.environ["CN_ADMIN_TOKEN"] = "test-admin-token"
    admin_headers = {"X-Admin-Token": "test-admin-token"}

    now = datetime.now(timezone.utc)
    source_id = uuid4()
    item_a = uuid4()
    item_b = uuid4()
    cluster_a = uuid4()
    cluster_b = uuid4()
    topic_from = uuid4()

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sources(id, name, source_type, active) VALUES (%s,%s,%s,%s);",
            (source_id, "Example News", "journalism", True),
        )
        for item_id, url, title in [
            (item_a, "https://example.com/a", "Item A"),
            (item_b, "https://example.com/b", "Item B"),
        ]:
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
                    url,
                    title,
                    now,
                    now,
                    "news",
                    "en",
                    _sha256_hex(title),
                    _sha256_hex(url),
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
            (cluster_a, "active", "Cluster A", item_a, 1, 1, 1, 0, 0, 0.0, 0.0),
        )
        cur.execute(
            """
            INSERT INTO story_clusters(
              id, status, canonical_title, representative_item_id,
              distinct_source_count, distinct_source_type_count, item_count,
              velocity_6h, velocity_24h, trending_score, recency_score
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (cluster_b, "active", "Cluster B", item_b, 1, 1, 1, 0, 0, 0.0, 0.0),
        )
        cur.execute(
            "INSERT INTO cluster_items(cluster_id, item_id, role) VALUES (%s,%s,%s);",
            (cluster_a, item_a, "primary"),
        )
        cur.execute(
            "INSERT INTO cluster_items(cluster_id, item_id, role) VALUES (%s,%s,%s);",
            (cluster_b, item_b, "primary"),
        )
        cur.execute("INSERT INTO topics(id, name) VALUES (%s,%s);", (topic_from, "OldTopic"))

    # Public feedback (auth optional)
    resp = client.post(
        "/v1/feedback",
        json={"feedback_type": "confusing", "cluster_id": str(cluster_a), "message": "unclear"},
    )
    assert resp.status_code == 202, resp.text
    fid = resp.json()["feedback_id"]

    # Admin feedback list + patch
    resp = client.get("/v1/admin/feedback?status=new&page=1&page_size=10", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"][0]["feedback_id"] == fid

    resp = client.patch(
        f"/v1/admin/feedback/{fid}",
        headers=admin_headers,
        json={"status": "resolved", "resolution_notes": "ok"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "resolved"

    # Admin create topic + merge topic -> public redirect
    resp = client.post(
        "/v1/admin/topics",
        headers=admin_headers,
        json={"name": "NewTopic", "description_short": "d", "aliases": ["OldTopic"]},
    )
    assert resp.status_code == 200, resp.text
    to_topic = resp.json()["topic_id"]

    # Nullable patch fields should be clearable via explicit null.
    resp = client.patch(
        f"/v1/admin/topics/{to_topic}",
        headers=admin_headers,
        json={"description_short": None},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["description_short"] is None

    resp = client.post(
        f"/v1/admin/topics/{topic_from}/merge",
        headers=admin_headers,
        json={"to_topic_id": to_topic, "notes": "merge"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["from_topic_id"] == str(topic_from)

    resp = client.get(f"/v1/topics/{topic_from}")
    assert resp.status_code == 301, resp.text
    assert resp.json()["redirect_to_topic_id"] == to_topic

    # Admin set cluster topics (locked)
    resp = client.put(
        f"/v1/admin/clusters/{cluster_b}/topics",
        headers=admin_headers,
        json={"replace": True, "topics": [{"topic_id": to_topic, "score": 1.0, "locked": True}]},
    )
    assert resp.status_code == 200, resp.text

    # Cluster patch should allow clearing nullable fields.
    resp = client.patch(
        f"/v1/admin/clusters/{cluster_b}",
        headers=admin_headers,
        json={
            "takeaway": "Editorial note",
            "takeaway_supporting_item_ids": [str(item_b)],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["takeaway"] == "Editorial note"
    assert resp.json()["takeaway_supporting_item_ids"] == [str(item_b)]

    resp = client.patch(
        f"/v1/admin/clusters/{cluster_b}",
        headers=admin_headers,
        json={"takeaway": None},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["takeaway"] is None
    assert resp.json()["takeaway_supporting_item_ids"] == []

    # Admin merge cluster A -> B; A should redirect.
    resp = client.post(
        f"/v1/admin/clusters/{cluster_a}/merge",
        headers=admin_headers,
        json={
            "to_cluster_id": str(cluster_b),
            "notes": "dedupe",
            "supporting_item_ids": [str(item_a)],
        },
    )
    assert resp.status_code == 200, resp.text
    resp = client.get(f"/v1/clusters/{cluster_a}")
    assert resp.status_code == 301, resp.text
    assert resp.json()["redirect_to_cluster_id"] == str(cluster_b)

    # Admin lineage node + edge
    resp = client.post(
        "/v1/admin/lineage/nodes",
        headers=admin_headers,
        json={"node_type": "paper", "title": "Paper A", "external_url": "https://example.com/paper"},
    )
    assert resp.status_code == 200, resp.text
    node1 = resp.json()["node_id"]
    resp = client.post(
        "/v1/admin/lineage/nodes",
        headers=admin_headers,
        json={"node_type": "model", "title": "Model B"},
    )
    assert resp.status_code == 200, resp.text
    node2 = resp.json()["node_id"]
    resp = client.post(
        "/v1/admin/lineage/edges",
        headers=admin_headers,
        json={
            "from_node_id": node1,
            "to_node_id": node2,
            "relation_type": "extends",
            "evidence_item_ids": [str(item_b)],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["relation_type"] == "extends"
