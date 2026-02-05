from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from curious_now.api.schemas import ClusterCard, UserWatchesResponse, WatchedCluster
from curious_now.repo_stage2 import _cluster_cards_from_rows  # noqa: PLC2701


def watch_cluster(conn: psycopg.Connection[Any], *, user_id: UUID, cluster_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO user_cluster_watches(user_id, cluster_id) "
            "VALUES (%s,%s) ON CONFLICT DO NOTHING;",
            (user_id, cluster_id),
        )


def unwatch_cluster(conn: psycopg.Connection[Any], *, user_id: UUID, cluster_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_cluster_watches WHERE user_id = %s AND cluster_id = %s;",
            (user_id, cluster_id),
        )


def list_watches(conn: psycopg.Connection[Any], *, user_id: UUID) -> UserWatchesResponse:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              w.created_at AS watched_at,
              c.id AS cluster_id,
              c.canonical_title,
              c.updated_at,
              c.distinct_source_count,
              c.takeaway,
              c.confidence_band,
              c.method_badges,
              c.anti_hype_flags,
              (
                SELECT array_agg(DISTINCT i.content_type)
                FROM cluster_items ci
                JOIN items i ON i.id = ci.item_id
                WHERE ci.cluster_id = c.id
              ) AS content_type_badges
            FROM user_cluster_watches w
            JOIN story_clusters c ON c.id = w.cluster_id
            WHERE w.user_id = %s AND c.status = 'active'
            ORDER BY w.created_at DESC
            LIMIT 200;
            """,
            (user_id,),
        )
        rows = cur.fetchall()

    cards = _cluster_cards_from_rows(conn, rows)
    card_by_id: dict[UUID, ClusterCard] = {c.cluster_id: c for c in cards}
    watched = [
        WatchedCluster(watched_at=r["watched_at"], cluster=card_by_id[r["cluster_id"]])
        for r in rows
    ]
    return UserWatchesResponse(watched=watched)
