from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from curious_now.api.schemas import (
    ClusterUpdateEntry,
    ClusterUpdatesResponse,
    LineageEdge,
    LineageNode,
    TopicLineageResponse,
)


def get_cluster_updates(
    conn: psycopg.Connection[Any], *, cluster_id: UUID
) -> ClusterUpdatesResponse:
    # Verify cluster is active before returning updates
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM story_clusters WHERE id = %s AND status = 'active';",
            (cluster_id,),
        )
        if cur.fetchone() is None:
            return ClusterUpdatesResponse(cluster_id=cluster_id, updates=[])

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT created_at, change_type, summary, diff, supporting_item_ids
            FROM update_log_entries
            WHERE cluster_id = %s
            ORDER BY created_at DESC
            LIMIT 100;
            """,
            (cluster_id,),
        )
        rows = cur.fetchall()

    updates = [
        ClusterUpdateEntry(
            created_at=r["created_at"],
            change_type=r["change_type"],
            summary=r["summary"],
            diff=r["diff"] if isinstance(r["diff"], dict) else None,
            supporting_item_ids=list(r.get("supporting_item_ids") or []),
        )
        for r in rows
    ]
    return ClusterUpdatesResponse(cluster_id=cluster_id, updates=updates)


def get_topic_lineage(conn: psycopg.Connection[Any], *, topic_id: UUID) -> TopicLineageResponse:
    topic_token = str(topic_id)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id AS node_id, node_type, title, external_url
            FROM lineage_nodes
            WHERE topic_ids ? %s
            ORDER BY published_at DESC NULLS LAST, updated_at DESC
            LIMIT 200;
            """,
            (topic_token,),
        )
        node_rows = cur.fetchall()

    node_ids = [r["node_id"] for r in node_rows]
    if not node_ids:
        return TopicLineageResponse(topic_id=topic_id, nodes=[], edges=[])

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT from_node_id, to_node_id, relation_type, evidence_item_ids, notes_short
            FROM lineage_edges
            WHERE from_node_id = ANY(%s) AND to_node_id = ANY(%s)
            ORDER BY created_at DESC
            LIMIT 500;
            """,
            (node_ids, node_ids),
        )
        edge_rows = cur.fetchall()

    nodes = [
        LineageNode(
            node_id=r["node_id"],
            title=r["title"],
            node_type=r["node_type"],
            external_url=r["external_url"],
        )
        for r in node_rows
    ]

    edges = [
        LineageEdge(
            **{
                "from": r["from_node_id"],
                "to": r["to_node_id"],
                "relation_type": r["relation_type"],
                "evidence_item_ids": list(r.get("evidence_item_ids") or []),
                "notes_short": r["notes_short"],
            }
        )
        for r in edge_rows
    ]

    return TopicLineageResponse(topic_id=topic_id, nodes=nodes, edges=edges)
