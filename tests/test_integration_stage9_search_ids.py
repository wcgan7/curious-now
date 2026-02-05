from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.mark.integration
def test_stage9_search_identifier_first(client, db_conn: psycopg.Connection) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(timezone.utc)
    source_id = uuid4()

    doi = "10.1234/example.doi"
    arxiv = "2401.12345"

    item_doi = uuid4()
    cluster_doi = uuid4()
    item_arxiv = uuid4()
    cluster_arxiv = uuid4()

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sources(id, name, source_type, active) VALUES (%s,%s,%s,%s);",
            (source_id, "Example News", "journalism", True),
        )

        cur.execute(
            """
            INSERT INTO items(
              id, source_id, url, canonical_url, title, published_at, fetched_at,
              content_type, language, title_hash, canonical_hash, doi
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (
                item_doi,
                source_id,
                "https://example.com/doi",
                "https://example.com/doi",
                "DOI item",
                now,
                now,
                "peer_reviewed",
                "en",
                _sha256_hex("DOI item"),
                _sha256_hex("https://example.com/doi"),
                doi,
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
            (cluster_doi, "active", "DOI cluster", item_doi, 1, 1, 1, 0, 0, 0.0, 0.0),
        )
        cur.execute(
            "INSERT INTO cluster_items(cluster_id, item_id, role) VALUES (%s,%s,%s);",
            (cluster_doi, item_doi, "primary"),
        )

        cur.execute(
            """
            INSERT INTO items(
              id, source_id, url, canonical_url, title, published_at, fetched_at,
              content_type, language, title_hash, canonical_hash, arxiv_id
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (
                item_arxiv,
                source_id,
                "https://example.com/arxiv",
                "https://example.com/arxiv",
                "arXiv item",
                now,
                now,
                "preprint",
                "en",
                _sha256_hex("arXiv item"),
                _sha256_hex("https://example.com/arxiv"),
                arxiv,
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
                cluster_arxiv,
                "active",
                "arXiv cluster",
                item_arxiv,
                1,
                1,
                1,
                0,
                0,
                0.0,
                0.0,
            ),
        )
        cur.execute(
            "INSERT INTO cluster_items(cluster_id, item_id, role) VALUES (%s,%s,%s);",
            (cluster_arxiv, item_arxiv, "primary"),
        )

    resp = client.get("/v1/search", params={"q": doi})
    assert resp.status_code == 200, resp.text
    ids = [c["cluster_id"] for c in resp.json()["clusters"]]
    assert str(cluster_doi) in ids

    resp = client.get("/v1/search", params={"q": arxiv})
    assert resp.status_code == 200, resp.text
    ids = [c["cluster_id"] for c in resp.json()["clusters"]]
    assert str(cluster_arxiv) in ids

