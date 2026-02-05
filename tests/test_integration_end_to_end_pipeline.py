from __future__ import annotations

import threading
from collections.abc import Generator
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from curious_now.clustering import cluster_unassigned_items
from curious_now.ingestion import ingest_due_feeds
from curious_now.topic_tagging import load_topic_seed, seed_topics, tag_recent_clusters


@pytest.fixture()
def rss_feed_url_two_items() -> Generator[str, None, None]:
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <description>Test</description>
    <item>
      <title>AI model improves weather prediction</title>
      <link>https://example.com/story-1</link>
      <pubDate>Mon, 03 Feb 2026 00:00:00 GMT</pubDate>
    </item>
    <item>
      <title>AI model improves weather prediction</title>
      <link>https://example.com/story-2</link>
      <pubDate>Mon, 03 Feb 2026 01:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""
    rss_bytes = rss.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(rss_bytes)))
            self.end_headers()
            self.wfile.write(rss_bytes)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/rss.xml"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.mark.integration
def test_end_to_end_pipeline_ingest_cluster_tag(
    client: TestClient,
    db_conn: psycopg.Connection[Any],
    rss_feed_url_two_items: str,
) -> None:
    now = datetime.now(timezone.utc)
    source_id = uuid4()
    feed_id = uuid4()

    # Seed topics so Stage 2 tagging has something to attach.
    topics = load_topic_seed()
    seed_topics(db_conn, topics=topics, now_utc=now)

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources(id, name, source_type, active)
            VALUES (%s,%s,%s,%s);
            """,
            (source_id, "Test Source", "journalism", True),
        )
        cur.execute(
            """
            INSERT INTO source_feeds(
              id, source_id, feed_url, feed_type, fetch_interval_minutes, active
            )
            VALUES (%s,%s,%s,%s,%s,%s);
            """,
            (feed_id, source_id, rss_feed_url_two_items, "rss", 30, True),
        )

    # Stage 1: ingest
    ing = ingest_due_feeds(db_conn, now_utc=now, feed_id=feed_id, force=True)
    assert ing.items_inserted == 2

    # Stage 2: cluster
    clustered = cluster_unassigned_items(db_conn, now_utc=now, limit_items=50)
    assert clustered.items_processed == 2
    assert clustered.clusters_created == 1

    # Stage 2: topic tagging
    tagged = tag_recent_clusters(db_conn, now_utc=now, lookback_days=30, limit_clusters=50)
    assert tagged.clusters_scanned >= 1

    # Feed should return the cluster (and include at least one topic).
    resp = client.get("/v1/feed?tab=latest&page=1&page_size=10")
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert len(results) == 1
    cluster_id = results[0]["cluster_id"]
    assert any(t["name"] == "Artificial Intelligence" for t in results[0]["top_topics"])

    # Cluster detail should show evidence.
    resp = client.get(f"/v1/clusters/{cluster_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    evidence = body.get("evidence") or {}
    assert sum(len(v) for v in evidence.values()) == 2

    # Search should return the cluster.
    resp = client.get("/v1/search?q=AI%20model")
    assert resp.status_code == 200, resp.text
    clusters = resp.json()["clusters"]
    assert len(clusters) >= 1
    assert any(c["cluster_id"] == cluster_id for c in clusters)
