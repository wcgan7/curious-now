from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import psycopg
import pytest
import redis
from fastapi.testclient import TestClient

from curious_now.cache import clear_redis_client_cache


@pytest.mark.integration
def test_stage7_redis_cache_and_etag_for_cluster_detail(
    client: TestClient, db_conn: psycopg.Connection[Any]
) -> None:
    redis_url = os.environ.get("CN_REDIS_URL")
    if not redis_url:
        pytest.skip("CN_REDIS_URL not set")

    # Ensure client + cache layer reads fresh env.
    clear_redis_client_cache()

    r = redis.Redis.from_url(redis_url)
    r.flushdb()

    topic_id = uuid4()
    cluster_id = uuid4()
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO topics(id, name) VALUES (%s,%s);", (topic_id, "AI"))
        cur.execute(
            """
            INSERT INTO story_clusters(
              id, status, canonical_title,
              distinct_source_count, distinct_source_type_count, item_count,
              velocity_6h, velocity_24h, trending_score, recency_score
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (cluster_id, "active", "Cached Cluster", 0, 0, 0, 0, 0, 0.0, 0.0),
        )
        cur.execute(
            "INSERT INTO cluster_topics(cluster_id, topic_id, score) VALUES (%s,%s,%s);",
            (cluster_id, topic_id, 1.0),
        )

    # First request: cache miss, should populate Redis and return ETag.
    resp1 = client.get(f"/v1/clusters/{cluster_id}")
    assert resp1.status_code == 200, resp1.text
    assert resp1.headers.get("x-cache") == "miss"
    etag = resp1.headers.get("etag")
    assert etag

    # Second request: cache hit.
    resp2 = client.get(f"/v1/clusters/{cluster_id}")
    assert resp2.status_code == 200, resp2.text
    assert resp2.headers.get("x-cache") == "hit"
    assert resp2.headers.get("etag") == etag

    # If-None-Match should yield 304.
    resp3 = client.get(f"/v1/clusters/{cluster_id}", headers={"If-None-Match": etag})
    assert resp3.status_code == 304
    assert resp3.headers.get("etag") == etag
