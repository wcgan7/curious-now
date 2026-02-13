from __future__ import annotations

import os
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


@pytest.mark.integration
def test_stage10_entities_and_experiments(client, db_conn: psycopg.Connection) -> None:  # type: ignore[no-untyped-def]
    os.environ["CN_ADMIN_TOKEN"] = "test-admin-token"
    admin_headers = {"X-Admin-Token": "test-admin-token"}

    # Create two entities
    resp = client.post(
        "/v1/admin/entities",
        headers=admin_headers,
        json={"entity_type": "model", "name": "ModelX", "description_short": "d"},
    )
    assert resp.status_code == 200, resp.text
    e1 = resp.json()["entity_id"]

    resp = client.post(
        "/v1/admin/entities",
        headers=admin_headers,
        json={"entity_type": "model", "name": "ModelY"},
    )
    assert resp.status_code == 200, resp.text
    e2 = resp.json()["entity_id"]

    # Anonymous entities list should include them.
    resp = client.get("/v1/entities?q=Model")
    assert resp.status_code == 200, resp.text
    ids = [e["entity_id"] for e in resp.json()["results"]]
    assert e1 in ids and e2 in ids

    # User/entity follows are optional in authless-first deployments.
    if _has_route("POST", "/v1/user/follows/entities/{entity_id}") and _has_route(
        "POST", "/v1/auth/magic_link/verify"
    ):
        _user_id, token = create_magic_link_token(db_conn, email="entity@example.com")
        resp = client.post("/v1/auth/magic_link/verify", json={"token": token})
        assert resp.status_code == 200, resp.text

        resp = client.post(f"/v1/user/follows/entities/{e2}")
        assert resp.status_code == 200, resp.text
        resp = client.get("/v1/user/follows/entities")
        assert resp.status_code == 200, resp.text
        assert resp.json()["entities"][0]["entity_id"] == e2

    # Merge e1 -> e2; e1 should redirect.
    resp = client.post(
        f"/v1/admin/entities/{e1}/merge",
        headers=admin_headers,
        json={"to_entity_id": e2, "notes": "dedupe"},
    )
    assert resp.status_code == 200, resp.text
    resp = client.get(f"/v1/entities/{e1}")
    assert resp.status_code == 301, resp.text
    assert resp.json()["redirect_to_entity_id"] == e2

    # Assign cluster -> entity mapping (locked)
    cluster_id = uuid4()
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO story_clusters(
              id, status, canonical_title,
              distinct_source_count, distinct_source_type_count, item_count,
              velocity_6h, velocity_24h, trending_score, recency_score
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (cluster_id, "active", "Entity Cluster", 0, 0, 0, 0, 0, 0.0, 0.0),
        )

    resp = client.put(
        f"/v1/admin/clusters/{cluster_id}/entities",
        headers=admin_headers,
        json={"replace": True, "entities": [{"entity_id": e2, "score": 1.0, "locked": True}]},
    )
    assert resp.status_code == 200, resp.text

    resp = client.get(f"/v1/entities/{e2}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["latest_clusters"][0]["cluster_id"] == str(cluster_id)

    # Experiments
    resp = client.post(
        "/v1/admin/experiments",
        headers=admin_headers,
        json={"key": "feed_ranking_v2", "description": "test", "active": True},
    )
    assert resp.status_code == 200, resp.text
    exp_id = resp.json()["experiment_id"]

    resp = client.patch(
        f"/v1/admin/experiments/{exp_id}",
        headers=admin_headers,
        json={"active": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["active"] is False

    # Nullable fields should be clearable via explicit null.
    resp = client.patch(
        f"/v1/admin/experiments/{exp_id}",
        headers=admin_headers,
        json={"description": None},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["description"] is None

    # Feature flags
    resp = client.put(
        "/v1/admin/feature_flags/semantic_search",
        headers=admin_headers,
        json={"enabled": True, "config": {"mode": "rerank"}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["key"] == "semantic_search"
    assert resp.json()["enabled"] is True

    # Partial updates should not clobber unspecified fields.
    resp = client.put(
        "/v1/admin/feature_flags/semantic_search",
        headers=admin_headers,
        json={"config": {"mode": "hybrid"}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True
    assert resp.json()["config"]["mode"] == "hybrid"

    resp = client.put(
        "/v1/admin/feature_flags/semantic_search",
        headers=admin_headers,
        json={"enabled": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is False
    assert resp.json()["config"]["mode"] == "hybrid"
