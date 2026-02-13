from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from curious_now.api.app import app
from curious_now.repo_stage5 import create_magic_link_token


def _has_route(method: str, path: str) -> bool:
    for route in app.router.routes:
        if getattr(route, "path", None) != path:
            continue
        methods: set[str] = set(getattr(route, "methods", set()))
        if method.upper() in methods:
            return True
    return False


pytestmark = pytest.mark.skipif(
    not _has_route("POST", "/v1/auth/magic_link/verify"),
    reason="Stage 5 auth/user routes are deferred for authless launch.",
)


@pytest.mark.integration
def test_stage5_magic_link_login_prefs_and_for_you(client, db_conn: psycopg.Connection) -> None:  # type: ignore[no-untyped-def]
    # Arrange minimal data: topic + cluster
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
            (cluster_id, "active", "For You Cluster", 0, 0, 0, 0, 0, 0.0, 0.0),
        )
        cur.execute(
            "INSERT INTO cluster_topics(cluster_id, topic_id, score) VALUES (%s,%s,%s);",
            (cluster_id, topic_id, 1.0),
        )

    # Unauthed for_you should 401
    resp = client.get("/v1/feed?tab=for_you")
    assert resp.status_code == 401

    # Create login token directly (since /auth/magic_link/start only logs tokens).
    _user_id, token = create_magic_link_token(db_conn, email="user@example.com")

    resp = client.post("/v1/auth/magic_link/verify", json={"token": token})
    assert resp.status_code == 200, resp.text
    assert "cn_session" in client.cookies

    # Current user
    resp = client.get("/v1/user")
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["email"] == "user@example.com"

    # Follow topic and see it reflected in prefs
    resp = client.post(f"/v1/user/follows/topics/{topic_id}")
    assert resp.status_code == 200, resp.text

    resp = client.get("/v1/user/prefs")
    assert resp.status_code == 200, resp.text
    prefs = resp.json()["prefs"]
    assert prefs["reading_mode_default"] in ("intuition", "deep")
    assert str(topic_id) in prefs["followed_topic_ids"]

    # for_you now returns the cluster
    resp = client.get("/v1/feed?tab=for_you&page=1&page_size=10")
    assert resp.status_code == 200, resp.text
    feed = resp.json()
    assert feed["tab"] == "for_you"
    assert feed["results"][0]["cluster_id"] == str(cluster_id)

    # Watch cluster and list watches (Stage 6)
    resp = client.post(f"/v1/user/watches/clusters/{cluster_id}")
    assert resp.status_code == 200, resp.text
    resp = client.get("/v1/user/watches/clusters")
    assert resp.status_code == 200, resp.text
    assert resp.json()["watched"][0]["cluster"]["cluster_id"] == str(cluster_id)

    # Save cluster and list saves
    resp = client.post(f"/v1/user/saves/{cluster_id}")
    assert resp.status_code == 200, resp.text
    resp = client.get("/v1/user/saves")
    assert resp.status_code == 200, resp.text
    assert resp.json()["saved"][0]["cluster"]["cluster_id"] == str(cluster_id)

    # Events ingestion
    resp = client.post(
        "/v1/events",
        json={"event_type": "open_cluster", "cluster_id": str(cluster_id), "meta": {}},
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "accepted"
