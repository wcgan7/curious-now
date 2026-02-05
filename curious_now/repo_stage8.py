from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now.api.schemas import (
    AdminClusterMergeRequest,
    AdminClusterMergeResponse,
    AdminClusterPatchRequest,
    AdminClusterSplitRequest,
    AdminClusterSplitResponse,
    AdminFeedbackListResponse,
    AdminFeedbackPatchRequest,
    AdminLineageEdgeCreateRequest,
    AdminLineageNodeCreateRequest,
    AdminSetClusterTopicsRequest,
    AdminTopicCreateRequest,
    AdminTopicMergeRequest,
    AdminTopicMergeResponse,
    AdminTopicPatchRequest,
    ClusterDetail,
    FeedbackIn,
    FeedbackReport,
    LineageEdge,
    LineageNode,
    RedirectResponse,
    Topic,
)
from curious_now.repo_stage2 import get_cluster_detail_or_redirect


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _insert_editorial_action(
    conn: psycopg.Connection[Any],
    *,
    action_type: str,
    target_cluster_id: UUID | None = None,
    target_topic_id: UUID | None = None,
    target_feedback_id: UUID | None = None,
    target_lineage_node_id: UUID | None = None,
    target_lineage_edge_id: UUID | None = None,
    notes: str | None = None,
    supporting_item_ids: list[UUID] | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO editorial_actions(
              actor_type,
              action_type,
              target_cluster_id,
              target_topic_id,
              target_feedback_id,
              target_lineage_node_id,
              target_lineage_edge_id,
              notes,
              supporting_item_ids,
              payload
            )
            VALUES ('admin_token', %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                action_type,
                target_cluster_id,
                target_topic_id,
                target_feedback_id,
                target_lineage_node_id,
                target_lineage_edge_id,
                notes,
                Jsonb([str(x) for x in (supporting_item_ids or [])]),
                Jsonb(payload or {}),
            ),
        )


def create_feedback(
    conn: psycopg.Connection[Any],
    *,
    user_id: UUID | None,
    req: FeedbackIn,
) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO feedback_reports(
              user_id, client_id, cluster_id, item_id, topic_id, feedback_type, message, meta
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id;
            """,
            (
                user_id,
                req.client_id,
                req.cluster_id,
                req.item_id,
                req.topic_id,
                req.feedback_type,
                req.message,
                Jsonb({}),
            ),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("failed to create feedback")
        return UUID(str(row["id"]))


def list_feedback(
    conn: psycopg.Connection[Any],
    *,
    status: str | None,
    page: int,
    page_size: int,
) -> AdminFeedbackListResponse:
    offset = (page - 1) * page_size
    where_sql = ""
    params: list[Any] = []
    if status:
        where_sql = "WHERE status = %s"
        params.append(status)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              id AS feedback_id,
              created_at,
              feedback_type,
              status,
              message,
              cluster_id,
              item_id,
              topic_id,
              user_id
            FROM feedback_reports
            {where_sql}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s;
            """,
            (*params, page_size, offset),
        )
        rows = cur.fetchall()

    results = [
        FeedbackReport(
            feedback_id=r["feedback_id"],
            created_at=r["created_at"],
            feedback_type=r["feedback_type"],
            status=r["status"],
            message=r["message"],
            cluster_id=r["cluster_id"],
            item_id=r["item_id"],
            topic_id=r["topic_id"],
            user_id=r["user_id"],
        )
        for r in rows
    ]
    return AdminFeedbackListResponse(page=page, results=results)


def patch_feedback(
    conn: psycopg.Connection[Any],
    *,
    feedback_id: UUID,
    patch: AdminFeedbackPatchRequest,
) -> FeedbackReport:
    now = _now_utc()
    fields: list[str] = []
    params: list[Any] = []
    if patch.status is not None:
        fields.append("status = %s")
        params.append(patch.status)
        if patch.status == "triaged":
            fields.append("triaged_at = %s")
            params.append(now)
        if patch.status in ("resolved", "ignored"):
            fields.append("resolved_at = %s")
            params.append(now)
    if patch.resolution_notes is not None:
        fields.append("resolution_notes = %s")
        params.append(patch.resolution_notes)
    if not fields:
        raise ValueError("no fields to patch")

    params.append(feedback_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE feedback_reports
            SET {', '.join(fields)}
            WHERE id = %s;
            """,
            params,
        )
        cur.execute(
            """
            SELECT
              id AS feedback_id,
              created_at,
              feedback_type,
              status,
              message,
              cluster_id,
              item_id,
              topic_id,
              user_id
            FROM feedback_reports
            WHERE id = %s;
            """,
            (feedback_id,),
        )
        row = cur.fetchone()
    if not row:
        raise KeyError("feedback not found")

    _insert_editorial_action(
        conn,
        action_type="resolve_feedback",
        target_feedback_id=feedback_id,
        notes=patch.resolution_notes,
        payload={"status": patch.status},
    )

    return FeedbackReport(
        feedback_id=row["feedback_id"],
        created_at=row["created_at"],
        feedback_type=row["feedback_type"],
        status=row["status"],
        message=row["message"],
        cluster_id=row["cluster_id"],
        item_id=row["item_id"],
        topic_id=row["topic_id"],
        user_id=row["user_id"],
    )


def topic_redirect_to(conn: psycopg.Connection[Any], *, topic_id: UUID) -> UUID | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT to_topic_id FROM topic_redirects WHERE from_topic_id = %s;",
            (topic_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return UUID(str(row["to_topic_id"]))


def admin_create_topic(conn: psycopg.Connection[Any], *, req: AdminTopicCreateRequest) -> Topic:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO topics(name, description_short, aliases, parent_topic_id)
            VALUES (%s,%s,%s,%s)
            RETURNING id AS topic_id, name, description_short;
            """,
            (req.name, req.description_short, Jsonb(req.aliases), req.parent_topic_id),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("failed to create topic")

    tid = row["topic_id"]
    _insert_editorial_action(conn, action_type="create_topic", target_topic_id=tid)
    return Topic(topic_id=tid, name=row["name"], description_short=row["description_short"])


def admin_patch_topic(
    conn: psycopg.Connection[Any], *, topic_id: UUID, req: AdminTopicPatchRequest
) -> Topic:
    fields: list[str] = []
    params: list[Any] = []
    fields_set = req.model_fields_set

    if "name" in fields_set:
        if req.name is None:
            raise ValueError("name cannot be null")
        fields.append("name = %s")
        params.append(req.name)
    if "description_short" in fields_set:
        fields.append("description_short = %s")
        params.append(req.description_short)
    if "aliases" in fields_set:
        if req.aliases is None:
            raise ValueError("aliases cannot be null")
        fields.append("aliases = %s")
        params.append(Jsonb(req.aliases))
    if "parent_topic_id" in fields_set:
        fields.append("parent_topic_id = %s")
        params.append(req.parent_topic_id)
    if not fields:
        raise ValueError("no fields to patch")

    fields.append("updated_at = now()")
    params.append(topic_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE topics SET {', '.join(fields)} WHERE id = %s;", params)
        cur.execute(
            "SELECT id AS topic_id, name, description_short FROM topics WHERE id = %s;",
            (topic_id,),
        )
        row = cur.fetchone()
    if not row:
        raise KeyError("topic not found")
    _insert_editorial_action(
        conn,
        action_type="rename_topic",
        target_topic_id=topic_id,
        payload=req.model_dump(mode="json", exclude_unset=True),
    )
    return Topic(
        topic_id=row["topic_id"],
        name=row["name"],
        description_short=row["description_short"],
    )


def admin_merge_topic(
    conn: psycopg.Connection[Any], *, from_topic_id: UUID, req: AdminTopicMergeRequest
) -> AdminTopicMergeResponse:
    if from_topic_id == req.to_topic_id:
        raise ValueError("cannot merge topic into itself")

    with conn.transaction():
        with conn.cursor() as cur:
            # Move associations, keeping existing ones.
            cur.execute(
                """
                INSERT INTO cluster_topics(cluster_id, topic_id, score, assignment_source, locked)
                SELECT cluster_id, %s, score, assignment_source, locked
                FROM cluster_topics
                WHERE topic_id = %s
                ON CONFLICT (cluster_id, topic_id) DO NOTHING;
                """,
                (req.to_topic_id, from_topic_id),
            )

            cur.execute(
                """
                INSERT INTO topic_redirects(from_topic_id, to_topic_id, redirect_type)
                VALUES (%s,%s,'merge')
                ON CONFLICT (from_topic_id) DO UPDATE SET to_topic_id = EXCLUDED.to_topic_id;
                """,
                (from_topic_id, req.to_topic_id),
            )

        _insert_editorial_action(
            conn,
            action_type="merge_topic",
            target_topic_id=req.to_topic_id,
            notes=req.notes,
            payload={"from_topic_id": str(from_topic_id)},
        )

    return AdminTopicMergeResponse(from_topic_id=from_topic_id, to_topic_id=req.to_topic_id)


def _recompute_cluster_counts(conn: psycopg.Connection[Any], *, cluster_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE story_clusters c
            SET
              item_count = (
                SELECT count(*) FROM cluster_items ci WHERE ci.cluster_id = c.id
              ),
              distinct_source_count = (
                SELECT count(DISTINCT i.source_id)
                FROM cluster_items ci
                JOIN items i ON i.id = ci.item_id
                WHERE ci.cluster_id = c.id
              ),
              distinct_source_type_count = (
                SELECT count(DISTINCT s.source_type)
                FROM cluster_items ci
                JOIN items i ON i.id = ci.item_id
                JOIN sources s ON s.id = i.source_id
                WHERE ci.cluster_id = c.id
              ),
              updated_at = now()
            WHERE c.id = %s;
            """,
            (cluster_id,),
        )


def admin_merge_cluster(
    conn: psycopg.Connection[Any], *, from_cluster_id: UUID, req: AdminClusterMergeRequest
) -> AdminClusterMergeResponse:
    if from_cluster_id == req.to_cluster_id:
        raise ValueError("cannot merge cluster into itself")

    with conn.transaction():
        with conn.cursor() as cur:
            # Move items (deduped by PK), then remove from source cluster.
            cur.execute(
                """
                INSERT INTO cluster_items(cluster_id, item_id, role)
                SELECT %s, item_id, role
                FROM cluster_items
                WHERE cluster_id = %s
                ON CONFLICT (cluster_id, item_id) DO NOTHING;
                """,
                (req.to_cluster_id, from_cluster_id),
            )
            cur.execute("DELETE FROM cluster_items WHERE cluster_id = %s;", (from_cluster_id,))

            # Merge topic assignments as well (keep existing).
            cur.execute(
                """
                INSERT INTO cluster_topics(cluster_id, topic_id, score, assignment_source, locked)
                SELECT %s, topic_id, score, assignment_source, locked
                FROM cluster_topics
                WHERE cluster_id = %s
                ON CONFLICT (cluster_id, topic_id) DO NOTHING;
                """,
                (req.to_cluster_id, from_cluster_id),
            )

            cur.execute(
                "UPDATE story_clusters SET status = 'merged', updated_at = now() WHERE id = %s;",
                (from_cluster_id,),
            )
            cur.execute(
                """
                INSERT INTO cluster_redirects(from_cluster_id, to_cluster_id, redirect_type)
                VALUES (%s,%s,'merge')
                ON CONFLICT (from_cluster_id) DO UPDATE SET to_cluster_id = EXCLUDED.to_cluster_id;
                """,
                (from_cluster_id, req.to_cluster_id),
            )

            # Update log entry on destination cluster.
            cur.execute(
                """
                INSERT INTO update_log_entries(
                  cluster_id, change_type, summary, diff, supporting_item_ids
                )
                VALUES (%s,'merge',%s,%s,%s);
                """,
                (
                    req.to_cluster_id,
                    f"Merged cluster {from_cluster_id} into this story.",
                    Jsonb({"from_cluster_id": str(from_cluster_id)}),
                    Jsonb([str(x) for x in req.supporting_item_ids]),
                ),
            )

        _recompute_cluster_counts(conn, cluster_id=req.to_cluster_id)

        _insert_editorial_action(
            conn,
            action_type="merge_cluster",
            target_cluster_id=req.to_cluster_id,
            notes=req.notes,
            supporting_item_ids=req.supporting_item_ids,
            payload={"from_cluster_id": str(from_cluster_id)},
        )

    return AdminClusterMergeResponse(
        from_cluster_id=from_cluster_id,
        to_cluster_id=req.to_cluster_id,
    )


def admin_split_cluster(
    conn: psycopg.Connection[Any], *, source_cluster_id: UUID, req: AdminClusterSplitRequest
) -> AdminClusterSplitResponse:
    if not req.move_item_ids:
        raise ValueError("move_item_ids must be non-empty")

    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO story_clusters(status, canonical_title)
                VALUES ('active', %s)
                RETURNING id;
                """,
                (req.new_cluster_title or "Split cluster",),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("failed to create split cluster")
            new_cluster_id = row["id"]

            cur.execute(
                """
                INSERT INTO cluster_items(cluster_id, item_id, role)
                SELECT %s, ci.item_id, ci.role
                FROM cluster_items ci
                WHERE ci.cluster_id = %s
                  AND ci.item_id = ANY(%s)
                ON CONFLICT (cluster_id, item_id) DO NOTHING;
                """,
                (new_cluster_id, source_cluster_id, req.move_item_ids),
            )
            cur.execute(
                """
                DELETE FROM cluster_items
                WHERE cluster_id = %s AND item_id = ANY(%s);
                """,
                (source_cluster_id, req.move_item_ids),
            )

            cur.execute(
                """
                INSERT INTO update_log_entries(
                  cluster_id, change_type, summary, diff, supporting_item_ids
                )
                VALUES (%s,'split',%s,%s,'[]'::jsonb);
                """,
                (
                    source_cluster_id,
                    f"Split out {len(req.move_item_ids)} items into a new story.",
                    Jsonb({"new_cluster_id": str(new_cluster_id)}),
                ),
            )
            cur.execute(
                """
                INSERT INTO update_log_entries(
                  cluster_id, change_type, summary, diff, supporting_item_ids
                )
                VALUES (%s,'split',%s,%s,'[]'::jsonb);
                """,
                (
                    new_cluster_id,
                    f"Created from a split of {source_cluster_id}.",
                    Jsonb({"source_cluster_id": str(source_cluster_id)}),
                ),
            )

        _recompute_cluster_counts(conn, cluster_id=source_cluster_id)
        _recompute_cluster_counts(conn, cluster_id=new_cluster_id)

        _insert_editorial_action(
            conn,
            action_type="split_cluster",
            target_cluster_id=source_cluster_id,
            notes=req.notes,
            payload={
                "new_cluster_id": str(new_cluster_id),
                "move_item_ids": [str(x) for x in req.move_item_ids],
            },
        )

    return AdminClusterSplitResponse(
        source_cluster_id=source_cluster_id,
        new_cluster_id=new_cluster_id,
    )


def admin_set_cluster_status(
    conn: psycopg.Connection[Any],
    *,
    cluster_id: UUID,
    status: str,
    change_type: str,
    notes: str | None,
) -> None:
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE story_clusters SET status = %s, updated_at = now() WHERE id = %s;",
                (status, cluster_id),
            )
            cur.execute(
                """
                INSERT INTO update_log_entries(
                  cluster_id, change_type, summary, diff, supporting_item_ids
                )
                VALUES (%s,%s,%s,%s,'[]'::jsonb);
                """,
                (cluster_id, change_type, notes or change_type, Jsonb({})),
            )
        _insert_editorial_action(
            conn,
            action_type=f"{change_type}_cluster",
            target_cluster_id=cluster_id,
            notes=notes,
        )


def admin_patch_cluster(
    conn: psycopg.Connection[Any],
    *,
    cluster_id: UUID,
    patch: AdminClusterPatchRequest,
) -> ClusterDetail:
    fields: list[str] = []
    params: list[Any] = []
    changed_cols: list[str] = []
    fields_set = patch.model_fields_set

    if "canonical_title" in fields_set:
        if patch.canonical_title is None:
            raise ValueError("canonical_title cannot be null")
        fields.append("canonical_title = %s")
        params.append(patch.canonical_title)
        changed_cols.append("canonical_title")
    if "representative_item_id" in fields_set:
        fields.append("representative_item_id = %s")
        params.append(patch.representative_item_id)
        changed_cols.append("representative_item_id")

    if "takeaway" in fields_set:
        fields.append("takeaway = %s")
        params.append(patch.takeaway)
        fields.append("takeaway_supporting_item_ids = %s")
        params.append(
            Jsonb([])
            if patch.takeaway is None
            else Jsonb([str(x) for x in patch.takeaway_supporting_item_ids])
        )
        changed_cols.extend(["takeaway", "takeaway_supporting_item_ids"])
    elif "takeaway_supporting_item_ids" in fields_set:
        fields.append("takeaway_supporting_item_ids = %s")
        params.append(Jsonb([str(x) for x in patch.takeaway_supporting_item_ids]))
        changed_cols.append("takeaway_supporting_item_ids")

    if "summary_intuition" in fields_set:
        fields.append("summary_intuition = %s")
        params.append(patch.summary_intuition)
        fields.append("summary_intuition_supporting_item_ids = %s")
        params.append(
            Jsonb([])
            if patch.summary_intuition is None
            else Jsonb([str(x) for x in patch.summary_intuition_supporting_item_ids])
        )
        changed_cols.extend(["summary_intuition", "summary_intuition_supporting_item_ids"])
    elif "summary_intuition_supporting_item_ids" in fields_set:
        fields.append("summary_intuition_supporting_item_ids = %s")
        params.append(Jsonb([str(x) for x in patch.summary_intuition_supporting_item_ids]))
        changed_cols.append("summary_intuition_supporting_item_ids")

    if "summary_deep_dive" in fields_set:
        fields.append("summary_deep_dive = %s")
        params.append(patch.summary_deep_dive)
        fields.append("summary_deep_dive_supporting_item_ids = %s")
        params.append(
            Jsonb([])
            if patch.summary_deep_dive is None
            else Jsonb([str(x) for x in patch.summary_deep_dive_supporting_item_ids])
        )
        changed_cols.extend(["summary_deep_dive", "summary_deep_dive_supporting_item_ids"])
    elif "summary_deep_dive_supporting_item_ids" in fields_set:
        fields.append("summary_deep_dive_supporting_item_ids = %s")
        params.append(Jsonb([str(x) for x in patch.summary_deep_dive_supporting_item_ids]))
        changed_cols.append("summary_deep_dive_supporting_item_ids")

    if "assumptions" in fields_set:
        fields.append("assumptions = %s")
        params.append(Jsonb(patch.assumptions))
        changed_cols.append("assumptions")
    if "limitations" in fields_set:
        fields.append("limitations = %s")
        params.append(Jsonb(patch.limitations))
        changed_cols.append("limitations")
    if "what_could_change_this" in fields_set:
        fields.append("what_could_change_this = %s")
        params.append(Jsonb(patch.what_could_change_this))
        changed_cols.append("what_could_change_this")
    if "confidence_band" in fields_set:
        fields.append("confidence_band = %s")
        params.append(patch.confidence_band)
        changed_cols.append("confidence_band")
    if "method_badges" in fields_set:
        fields.append("method_badges = %s")
        params.append(Jsonb(patch.method_badges))
        changed_cols.append("method_badges")
    if "anti_hype_flags" in fields_set:
        fields.append("anti_hype_flags = %s")
        params.append(Jsonb(patch.anti_hype_flags))
        changed_cols.append("anti_hype_flags")

    if not fields:
        raise ValueError("no fields to patch")
    fields.append("updated_at = now()")
    params.append(cluster_id)

    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(f"UPDATE story_clusters SET {', '.join(fields)} WHERE id = %s;", params)
            # Record as a correction update (v0).
            cur.execute(
                """
                INSERT INTO update_log_entries(
                  cluster_id, change_type, summary, diff, supporting_item_ids
                )
                VALUES (%s,'correction',%s,%s,%s);
                """,
                (
                    cluster_id,
                    "Editorial correction.",
                    Jsonb({"fields": changed_cols}),
                    Jsonb(
                        [str(x) for x in (patch.takeaway_supporting_item_ids or [])]
                        + [str(x) for x in (patch.summary_intuition_supporting_item_ids or [])]
                        + [str(x) for x in (patch.summary_deep_dive_supporting_item_ids or [])]
                    ),
                ),
            )

        _insert_editorial_action(
            conn,
            action_type="correct_cluster",
            target_cluster_id=cluster_id,
            notes=None,
            supporting_item_ids=(patch.takeaway_supporting_item_ids or [])
            + (patch.summary_intuition_supporting_item_ids or [])
            + (patch.summary_deep_dive_supporting_item_ids or []),
            payload=patch.model_dump(mode="json", exclude_unset=True),
        )

    detail = get_cluster_detail_or_redirect(conn, cluster_id=cluster_id)
    if isinstance(detail, RedirectResponse):
        raise RuntimeError("unexpected redirect for patched cluster")
    return detail


def admin_set_cluster_topics(
    conn: psycopg.Connection[Any], *, cluster_id: UUID, req: AdminSetClusterTopicsRequest
) -> None:
    with conn.transaction():
        with conn.cursor() as cur:
            if req.replace:
                cur.execute("DELETE FROM cluster_topics WHERE cluster_id = %s;", (cluster_id,))
            for t in req.topics:
                cur.execute(
                    """
                    INSERT INTO cluster_topics(
                      cluster_id, topic_id, score, assignment_source, locked
                    )
                    VALUES (%s,%s,%s,'editor',%s)
                    ON CONFLICT (cluster_id, topic_id)
                    DO UPDATE SET
                      score = EXCLUDED.score,
                      assignment_source = 'editor',
                      locked = EXCLUDED.locked;
                    """,
                    (
                        cluster_id,
                        t.topic_id,
                        float(t.score) if t.score is not None else 1.0,
                        bool(t.locked) if t.locked is not None else True,
                    ),
                )

            cur.execute(
                "UPDATE story_clusters SET updated_at = now() WHERE id = %s;",
                (cluster_id,),
            )

        _insert_editorial_action(
            conn,
            action_type="set_cluster_topics",
            target_cluster_id=cluster_id,
            notes=req.notes,
            payload=req.model_dump(mode="json"),
        )


def admin_create_lineage_node(
    conn: psycopg.Connection[Any], *, req: AdminLineageNodeCreateRequest
) -> LineageNode:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO lineage_nodes(
              node_type, title, external_url, published_at, external_ids, topic_ids
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING id;
            """,
            (
                req.node_type,
                req.title,
                req.external_url,
                req.published_at,
                Jsonb(req.external_ids) if req.external_ids is not None else None,
                Jsonb([str(x) for x in req.topic_ids]) if req.topic_ids else None,
            ),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("failed to create lineage node")
    node_id = row["id"]

    _insert_editorial_action(
        conn,
        action_type="create_lineage_node",
        target_lineage_node_id=node_id,
        payload=req.model_dump(mode="json"),
    )
    return LineageNode(
        node_id=node_id,
        node_type=req.node_type,
        title=req.title,
        external_url=req.external_url,
        published_at=req.published_at,
    )


def admin_create_lineage_edge(
    conn: psycopg.Connection[Any], *, req: AdminLineageEdgeCreateRequest
) -> LineageEdge:
    if not req.evidence_item_ids:
        raise ValueError("evidence_item_ids must be non-empty")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO lineage_edges(
              from_node_id, to_node_id, relation_type, evidence_item_ids, notes_short
            )
            VALUES (%s,%s,%s,%s,%s)
            RETURNING id;
            """,
            (
                req.from_node_id,
                req.to_node_id,
                req.relation_type,
                Jsonb([str(x) for x in req.evidence_item_ids]),
                req.notes_short,
            ),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("failed to create lineage edge")
    edge_id = row["id"]

    _insert_editorial_action(
        conn,
        action_type="create_lineage_edge",
        target_lineage_edge_id=edge_id,
        supporting_item_ids=req.evidence_item_ids,
        payload=req.model_dump(mode="json"),
    )
    return LineageEdge.model_validate(
        {
            "from": req.from_node_id,
            "to": req.to_node_id,
            "relation_type": req.relation_type,
            "evidence_item_ids": req.evidence_item_ids,
            "notes_short": req.notes_short,
        }
    )
