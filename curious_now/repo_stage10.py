from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now.api.schemas import (
    AdminEntityCreateRequest,
    AdminEntityMergeRequest,
    AdminEntityMergeResponse,
    AdminEntityPatchRequest,
    AdminExperimentCreateRequest,
    AdminExperimentPatchRequest,
    AdminFeatureFlagUpsertRequest,
    AdminSetClusterEntitiesRequest,
    EntitiesResponse,
    Entity,
    EntityDetail,
    Experiment,
    FeatureFlag,
    UserFollowedEntitiesResponse,
)
from curious_now.repo_stage2 import _cluster_cards_from_rows  # noqa: PLC2701


def _row_get(row: Any, key: str, idx: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[idx]


def entity_redirect_to(conn: psycopg.Connection[Any], *, entity_id: UUID) -> UUID | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT to_entity_id FROM entity_redirects WHERE from_entity_id = %s;",
            (entity_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return UUID(str(_row_get(row, "to_entity_id", 0)))


def list_entities(
    conn: psycopg.Connection[Any],
    *,
    q: str | None,
    entity_type: str | None,
    page: int,
    page_size: int,
    user_id: UUID | None,
) -> EntitiesResponse:
    offset = (page - 1) * page_size
    where: list[str] = []
    params: list[Any] = []

    if entity_type:
        where.append("e.entity_type = %s")
        params.append(entity_type)
    if q:
        where.append(
            "(e.name ILIKE %s OR EXISTS (SELECT 1 FROM entity_aliases a "
            "WHERE a.entity_id = e.id AND a.alias ILIKE %s))"
        )
        like = f"%{q.strip()}%"
        params.extend([like, like])

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    is_followed_sql = "NULL::boolean AS is_followed"
    if user_id is not None:
        is_followed_sql = (
            "EXISTS (SELECT 1 FROM user_entity_follows f "
            "WHERE f.user_id = %s AND f.entity_id = e.id) AS is_followed"
        )
        params = [user_id, *params]

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              e.id AS entity_id,
              e.entity_type,
              e.name,
              e.description_short,
              e.external_url,
              {is_followed_sql}
            FROM entities e
            {where_sql}
            ORDER BY e.name ASC
            LIMIT %s OFFSET %s;
            """,
            (*params, page_size, offset),
        )
        rows = cur.fetchall()

    results = [
        Entity(
            entity_id=r["entity_id"],
            entity_type=r["entity_type"],
            name=r["name"],
            description_short=r["description_short"],
            external_url=r["external_url"],
            is_followed=r.get("is_followed"),
        )
        for r in rows
    ]
    return EntitiesResponse(page=page, results=results)


def get_entity_detail_or_redirect(
    conn: psycopg.Connection[Any], *, entity_id: UUID, user_id: UUID | None
) -> EntityDetail | UUID:
    to_id = entity_redirect_to(conn, entity_id=entity_id)
    if to_id:
        return to_id

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id AS entity_id, entity_type, name, description_short, external_url
            FROM entities
            WHERE id = %s;
            """,
            (entity_id,),
        )
        row = cur.fetchone()
    if not row:
        raise KeyError("entity not found")

    is_followed: bool | None = None
    if user_id is not None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM user_entity_follows WHERE user_id = %s AND entity_id = %s;",
                (user_id, entity_id),
            )
            is_followed = cur.fetchone() is not None

    # Latest clusters linked to this entity.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
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
            FROM cluster_entities ce
            JOIN story_clusters c ON c.id = ce.cluster_id
            WHERE ce.entity_id = %s AND c.status = 'active'
            ORDER BY c.updated_at DESC
            LIMIT 20;
            """,
            (entity_id,),
        )
        cluster_rows = cur.fetchall()
    latest_clusters = _cluster_cards_from_rows(conn, cluster_rows)

    # Related entities (both directions).
    related: list[Entity] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT
              other.id AS entity_id,
              other.entity_type,
              other.name,
              other.description_short,
              other.external_url
            FROM entity_edges ee
            JOIN entities other ON other.id = CASE
              WHEN ee.from_entity_id = %s THEN ee.to_entity_id
              ELSE ee.from_entity_id
            END
            WHERE ee.from_entity_id = %s OR ee.to_entity_id = %s
            LIMIT 25;
            """,
            (entity_id, entity_id, entity_id),
        )
        related_rows = cur.fetchall()

    followed_set: set[UUID] = set()
    if user_id is not None and related_rows:
        ids = [r["entity_id"] for r in related_rows]
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT entity_id
                FROM user_entity_follows
                WHERE user_id = %s AND entity_id = ANY(%s);
                """,
                (user_id, ids),
            )
            followed_set = {UUID(str(x["entity_id"])) for x in cur.fetchall()}

    for r in related_rows:
        rid = UUID(str(r["entity_id"]))
        related.append(
            Entity(
                entity_id=rid,
                entity_type=r["entity_type"],
                name=r["name"],
                description_short=r["description_short"],
                external_url=r["external_url"],
                is_followed=(rid in followed_set) if user_id is not None else None,
            )
        )

    return EntityDetail(
        entity_id=row["entity_id"],
        entity_type=row["entity_type"],
        name=row["name"],
        description_short=row["description_short"],
        external_url=row["external_url"],
        is_followed=is_followed,
        latest_clusters=latest_clusters,
        related_entities=related,
    )


def follow_entity(conn: psycopg.Connection[Any], *, user_id: UUID, entity_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_entity_follows(user_id, entity_id)
            VALUES (%s,%s)
            ON CONFLICT DO NOTHING;
            """,
            (user_id, entity_id),
        )


def unfollow_entity(conn: psycopg.Connection[Any], *, user_id: UUID, entity_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_entity_follows WHERE user_id = %s AND entity_id = %s;",
            (user_id, entity_id),
        )


def list_followed_entities(
    conn: psycopg.Connection[Any], *, user_id: UUID
) -> UserFollowedEntitiesResponse:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              e.id AS entity_id,
              e.entity_type,
              e.name,
              e.description_short,
              e.external_url
            FROM user_entity_follows f
            JOIN entities e ON e.id = f.entity_id
            WHERE f.user_id = %s
            ORDER BY e.name ASC;
            """,
            (user_id,),
        )
        rows = cur.fetchall()

    entities = [
        Entity(
            entity_id=r["entity_id"],
            entity_type=r["entity_type"],
            name=r["name"],
            description_short=r["description_short"],
            external_url=r["external_url"],
            is_followed=True,
        )
        for r in rows
    ]
    return UserFollowedEntitiesResponse(entities=entities)


def admin_create_entity(conn: psycopg.Connection[Any], *, req: AdminEntityCreateRequest) -> Entity:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entities(entity_type, name, description_short, external_url)
            VALUES (%s,%s,%s,%s)
            RETURNING id AS entity_id, entity_type, name, description_short, external_url;
            """,
            (req.entity_type.value, req.name, req.description_short, req.external_url),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("failed to create entity")
    return Entity(
        entity_id=row["entity_id"],
        entity_type=row["entity_type"],
        name=row["name"],
        description_short=row["description_short"],
        external_url=row["external_url"],
        is_followed=None,
    )


def admin_patch_entity(
    conn: psycopg.Connection[Any], *, entity_id: UUID, req: AdminEntityPatchRequest
) -> Entity:
    fields: list[str] = []
    params: list[Any] = []
    fields_set = req.model_fields_set

    if "entity_type" in fields_set:
        if req.entity_type is None:
            raise ValueError("entity_type cannot be null")
        fields.append("entity_type = %s")
        params.append(req.entity_type.value)
    if "name" in fields_set:
        if req.name is None:
            raise ValueError("name cannot be null")
        fields.append("name = %s")
        params.append(req.name)
    if "description_short" in fields_set:
        fields.append("description_short = %s")
        params.append(req.description_short)
    if "external_url" in fields_set:
        fields.append("external_url = %s")
        params.append(req.external_url)
    if not fields:
        raise ValueError("no fields to patch")
    params.append(entity_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE entities SET {', '.join(fields)} WHERE id = %s;", params)
        cur.execute(
            """
            SELECT id AS entity_id, entity_type, name, description_short, external_url
            FROM entities
            WHERE id = %s;
            """,
            (entity_id,),
        )
        row = cur.fetchone()
    if not row:
        raise KeyError("entity not found")
    return Entity(
        entity_id=row["entity_id"],
        entity_type=row["entity_type"],
        name=row["name"],
        description_short=row["description_short"],
        external_url=row["external_url"],
        is_followed=None,
    )


def admin_merge_entity(
    conn: psycopg.Connection[Any], *, from_entity_id: UUID, req: AdminEntityMergeRequest
) -> AdminEntityMergeResponse:
    if from_entity_id == req.to_entity_id:
        raise ValueError("cannot merge entity into itself")

    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_entity_follows(user_id, entity_id)
                SELECT user_id, %s
                FROM user_entity_follows
                WHERE entity_id = %s
                ON CONFLICT DO NOTHING;
                """,
                (req.to_entity_id, from_entity_id),
            )
            cur.execute("DELETE FROM user_entity_follows WHERE entity_id = %s;", (from_entity_id,))

            cur.execute(
                """
                INSERT INTO cluster_entities(
                  cluster_id, entity_id, score, assignment_source, locked
                )
                SELECT cluster_id, %s, score, assignment_source, locked
                FROM cluster_entities
                WHERE entity_id = %s
                ON CONFLICT (cluster_id, entity_id) DO NOTHING;
                """,
                (req.to_entity_id, from_entity_id),
            )
            cur.execute("DELETE FROM cluster_entities WHERE entity_id = %s;", (from_entity_id,))

            cur.execute(
                """
                INSERT INTO entity_aliases(entity_id, alias)
                SELECT %s, alias
                FROM entity_aliases
                WHERE entity_id = %s
                ON CONFLICT DO NOTHING;
                """,
                (req.to_entity_id, from_entity_id),
            )
            cur.execute("DELETE FROM entity_aliases WHERE entity_id = %s;", (from_entity_id,))

            cur.execute(
                """
                UPDATE entity_edges
                SET from_entity_id = %s
                WHERE from_entity_id = %s;
                """,
                (req.to_entity_id, from_entity_id),
            )
            cur.execute(
                """
                UPDATE entity_edges
                SET to_entity_id = %s
                WHERE to_entity_id = %s;
                """,
                (req.to_entity_id, from_entity_id),
            )

            cur.execute(
                """
                INSERT INTO entity_redirects(from_entity_id, to_entity_id, redirect_type)
                VALUES (%s,%s,'merge')
                ON CONFLICT (from_entity_id) DO UPDATE SET to_entity_id = EXCLUDED.to_entity_id;
                """,
                (from_entity_id, req.to_entity_id),
            )

    return AdminEntityMergeResponse(from_entity_id=from_entity_id, to_entity_id=req.to_entity_id)


def admin_set_cluster_entities(
    conn: psycopg.Connection[Any], *, cluster_id: UUID, req: AdminSetClusterEntitiesRequest
) -> None:
    with conn.transaction():
        with conn.cursor() as cur:
            if req.replace:
                cur.execute("DELETE FROM cluster_entities WHERE cluster_id = %s;", (cluster_id,))
            for e in req.entities:
                cur.execute(
                    """
                    INSERT INTO cluster_entities(
                      cluster_id, entity_id, score, assignment_source, locked
                    )
                    VALUES (%s,%s,%s,'editor',%s)
                    ON CONFLICT (cluster_id, entity_id)
                    DO UPDATE SET
                      score = EXCLUDED.score,
                      assignment_source = 'editor',
                      locked = EXCLUDED.locked;
                    """,
                    (
                        cluster_id,
                        e.entity_id,
                        float(e.score) if e.score is not None else 1.0,
                        bool(e.locked) if e.locked is not None else True,
                    ),
                )


def admin_create_experiment(
    conn: psycopg.Connection[Any], *, req: AdminExperimentCreateRequest
) -> Experiment:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO experiments(key, description, active, start_at, end_at)
            VALUES (%s,%s,%s,%s,%s)
            RETURNING id AS experiment_id, key, description, active, start_at, end_at;
            """,
            (
                req.key,
                req.description,
                bool(req.active) if req.active is not None else False,
                req.start_at,
                req.end_at,
            ),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("failed to create experiment")
    return Experiment(
        experiment_id=row["experiment_id"],
        key=row["key"],
        description=row["description"],
        active=row["active"],
        start_at=row["start_at"],
        end_at=row["end_at"],
    )


def admin_patch_experiment(
    conn: psycopg.Connection[Any], *, experiment_id: UUID, req: AdminExperimentPatchRequest
) -> Experiment:
    fields: list[str] = []
    params: list[Any] = []
    fields_set = req.model_fields_set

    if "description" in fields_set:
        fields.append("description = %s")
        params.append(req.description)
    if "active" in fields_set:
        if req.active is None:
            raise ValueError("active cannot be null")
        fields.append("active = %s")
        params.append(req.active)
    if "start_at" in fields_set:
        fields.append("start_at = %s")
        params.append(req.start_at)
    if "end_at" in fields_set:
        fields.append("end_at = %s")
        params.append(req.end_at)
    if not fields:
        raise ValueError("no fields to patch")
    params.append(experiment_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE experiments SET {', '.join(fields)} WHERE id = %s;", params)
        cur.execute(
            """
            SELECT id AS experiment_id, key, description, active, start_at, end_at
            FROM experiments
            WHERE id = %s;
            """,
            (experiment_id,),
        )
        row = cur.fetchone()
    if not row:
        raise KeyError("experiment not found")
    return Experiment(
        experiment_id=row["experiment_id"],
        key=row["key"],
        description=row["description"],
        active=row["active"],
        start_at=row["start_at"],
        end_at=row["end_at"],
    )


def admin_upsert_feature_flag(
    conn: psycopg.Connection[Any], *, key: str, req: AdminFeatureFlagUpsertRequest
) -> FeatureFlag:
    fields_set = req.model_fields_set

    enabled: bool | None = None
    config: dict[str, Any] | None = None
    if "enabled" in fields_set:
        if req.enabled is None:
            raise ValueError("enabled cannot be null")
        enabled = bool(req.enabled)
    if "config" in fields_set:
        if req.config is None:
            raise ValueError("config cannot be null")
        config = req.config

    config_param = Jsonb(config) if config is not None else None
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO feature_flags(key, enabled, config)
            VALUES (
              %s,
              COALESCE(%s, false),
              COALESCE(%s::jsonb, '{}'::jsonb)
            )
            ON CONFLICT (key)
            DO UPDATE SET
              enabled = COALESCE(%s, feature_flags.enabled),
              config = COALESCE(%s::jsonb, feature_flags.config)
            RETURNING key, enabled, config;
            """,
            (key, enabled, config_param, enabled, config_param),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("failed to upsert feature flag")
    return FeatureFlag(key=row["key"], enabled=row["enabled"], config=row["config"] or {})
