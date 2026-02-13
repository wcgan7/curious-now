from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from curious_now.api.app import app
from curious_now.notifications import enqueue_cluster_update_jobs, send_due_notification_jobs
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
    not _has_route("POST", "/v1/user/watches/clusters/{cluster_id}"),
    reason="Stage 6 watch/notification user routes are deferred for authless launch.",
)


@pytest.mark.integration
def test_stage6_cluster_update_jobs_respect_prefs_and_quiet_hours(
    client: TestClient, db_conn: psycopg.Connection[Any]
) -> None:
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
            (cluster_id, "active", "Watched Cluster", 0, 0, 0, 0, 0, 0.0, 0.0),
        )
        cur.execute(
            "INSERT INTO cluster_topics(cluster_id, topic_id, score) VALUES (%s,%s,%s);",
            (cluster_id, topic_id, 1.0),
        )

    # Login, enable email notifications, and watch cluster.
    _user_id, token = create_magic_link_token(db_conn, email="notify@example.com")
    resp = client.post("/v1/auth/magic_link/verify", json={"token": token})
    assert resp.status_code == 200, resp.text

    resp = client.patch(
        "/v1/user/prefs",
        json={
            "notification_settings": {
                "email": {
                    "enabled": True,
                    "topic_digest_frequency": "off",
                    "story_update_alerts_enabled": True,
                },
                "timezone": "UTC",
                "quiet_hours": {"start": "22:00", "end": "08:00"},
                "limits": {"max_story_update_emails_per_day": 5},
            }
        },
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(f"/v1/user/watches/clusters/{cluster_id}")
    assert resp.status_code == 200, resp.text

    # Create an update log entry and enqueue a cluster_update job outside quiet hours.
    now = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    update_id = uuid4()
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO update_log_entries(
              id, cluster_id, created_at, change_type, summary, diff, supporting_item_ids
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s);
            """,
            (
                update_id,
                cluster_id,
                now,
                "refinement",
                "Updated summary",
                Jsonb({}),
                Jsonb([]),
            ),
        )

    inserted = enqueue_cluster_update_jobs(
        db_conn,
        since_utc=now - timedelta(seconds=1),
        now_utc=now,
    )
    assert inserted == 1

    with db_conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT notification_type, status, scheduled_for, payload
            FROM notification_jobs
            WHERE notification_type = 'cluster_update'
            ORDER BY created_at DESC
            LIMIT 1;
            """
        )
        job = cur.fetchone()
    assert job is not None
    assert job["status"] == "queued"
    assert job["scheduled_for"] <= now
    assert job["payload"]["update_log_entry_id"] == str(update_id)

    sent = send_due_notification_jobs(db_conn, now_utc=now, limit=10)
    assert sent == 1

    # Now enqueue another update inside quiet hours; it should schedule for 08:00 next day.
    now_quiet = datetime(2026, 2, 3, 23, 0, tzinfo=timezone.utc)
    update_id2 = uuid4()
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO update_log_entries(
              id, cluster_id, created_at, change_type, summary, diff, supporting_item_ids
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s);
            """,
            (
                update_id2,
                cluster_id,
                now_quiet,
                "refinement",
                "Another update",
                Jsonb({}),
                Jsonb([]),
            ),
        )

    inserted2 = enqueue_cluster_update_jobs(db_conn, since_utc=now_quiet, now_utc=now_quiet)
    assert inserted2 == 1

    with db_conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT scheduled_for, payload
            FROM notification_jobs
            WHERE payload->>'update_log_entry_id' = %s
            LIMIT 1;
            """,
            (str(update_id2),),
        )
        job2 = cur.fetchone()
    assert job2 is not None
    assert job2["scheduled_for"] == datetime(2026, 2, 4, 8, 0, tzinfo=timezone.utc)
