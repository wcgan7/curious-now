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

from curious_now.ingestion import ingest_due_feeds, normalize_url


@pytest.fixture()
def rss_feed_url() -> Generator[str, None, None]:
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <description>Test</description>
    <item>
      <title>Test story one</title>
      <link>https://example.com/story?utm_source=test</link>
      <pubDate>Mon, 03 Feb 2026 00:00:00 GMT</pubDate>
      <description><![CDATA[<p>Hello <b>world</b></p>]]></description>
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
def test_stage1_ingestion_worker_ingests_and_is_idempotent(
    client: TestClient,
    db_conn: psycopg.Connection[Any],
    rss_feed_url: str,
) -> None:
    now = datetime.now(timezone.utc)
    source_id = uuid4()
    feed_id = uuid4()

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
            (feed_id, source_id, rss_feed_url, "rss", 30, True),
        )

    # Ingest once.
    res1 = ingest_due_feeds(db_conn, now_utc=now, feed_id=feed_id, force=True)
    assert res1.feeds_attempted == 1
    assert res1.feeds_succeeded == 1
    assert res1.items_inserted == 1

    # API should show the item and canonical_url should be normalized.
    resp = client.get("/v1/items/feed?page=1&page_size=10")
    assert resp.status_code == 200, resp.text
    items = resp.json()["results"]
    assert len(items) == 1
    assert items[0]["canonical_url"] == normalize_url("https://example.com/story?utm_source=test")

    # Ingest again; should not create duplicates.
    res2 = ingest_due_feeds(db_conn, now_utc=now, feed_id=feed_id, force=True)
    assert res2.feeds_attempted == 1
    assert res2.feeds_succeeded == 1

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM items;")
        row = cur.fetchone()
        assert row is not None
        count = row[0] if not isinstance(row, dict) else list(row.values())[0]
        assert int(count) == 1
        cur.execute("SELECT count(*) FROM feed_fetch_logs WHERE feed_id = %s;", (feed_id,))
        row = cur.fetchone()
        assert row is not None
        count = row[0] if not isinstance(row, dict) else list(row.values())[0]
        assert int(count) == 2
