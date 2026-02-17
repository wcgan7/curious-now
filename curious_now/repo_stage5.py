from __future__ import annotations

import hashlib
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now.api.schemas import (
    ClusterCard,
    ClustersFeedResponse,
    SavedCluster,
    SimpleOkResponse,
    User,
    UserPrefs,
    UserPrefsResponse,
    UserResponse,
    UserSavesResponse,
    WhyInFeed,
)
from curious_now.repo_stage2 import _cluster_cards_from_rows  # noqa: PLC2701

_DEFAULT_NOTIFICATION_SETTINGS: dict[str, Any] = {
    "email": {
        "enabled": False,
        "topic_digest_frequency": "off",
        "story_update_alerts_enabled": False,
    },
    "timezone": "UTC",
    "quiet_hours": {"start": "22:00", "end": "08:00"},
    "limits": {"max_story_update_emails_per_day": 5},
}


def _deep_merge_defaults(value: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = deepcopy(defaults)
    for k, v in value.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge_defaults(v, merged[k])
        else:
            merged[k] = v
    return merged


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _row_get(row: Any, key: str, idx: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[idx]


def create_magic_link_token(
    conn: psycopg.Connection[Any],
    *,
    email: str,
    ttl_minutes: int = 15,
) -> tuple[UUID, str]:
    email_norm = normalize_email(email)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=ttl_minutes)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users(email_normalized, email_raw)
            VALUES (%s, %s)
            ON CONFLICT (email_normalized)
            DO UPDATE SET email_raw = EXCLUDED.email_raw
            RETURNING id;
            """,
            (email_norm, email),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("failed to upsert user")
        user_id = _row_get(row, "id", 0)

        cur.execute(
            "INSERT INTO user_prefs(user_id) VALUES (%s) ON CONFLICT DO NOTHING;",
            (user_id,),
        )

        token = secrets.token_urlsafe(32)
        token_hash = _sha256_hex(token)
        cur.execute(
            """
            INSERT INTO auth_magic_link_tokens(user_id, token_hash, expires_at)
            VALUES (%s, %s, %s);
            """,
            (user_id, token_hash, expires_at),
        )

    return user_id, token


def verify_magic_link_token(
    conn: psycopg.Connection[Any],
    *,
    token: str,
    session_ttl_days: int = 30,
) -> tuple[User, str]:
    token_hash = _sha256_hex(token)
    now = datetime.now(timezone.utc)
    session_expires_at = now + timedelta(days=session_ttl_days)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id AS token_id, t.user_id
            FROM auth_magic_link_tokens t
            WHERE t.token_hash = %s
              AND t.used_at IS NULL
              AND t.expires_at > now()
            LIMIT 1;
            """,
            (token_hash,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("invalid token")

        token_id = _row_get(row, "token_id", 0)
        user_id = _row_get(row, "user_id", 1)
        cur.execute("UPDATE auth_magic_link_tokens SET used_at = now() WHERE id = %s;", (token_id,))

        session_token = secrets.token_urlsafe(32)
        session_token_hash = _sha256_hex(session_token)
        cur.execute(
            """
            INSERT INTO user_sessions(user_id, session_token_hash, expires_at)
            VALUES (%s, %s, %s);
            """,
            (user_id, session_token_hash, session_expires_at),
        )

        cur.execute("UPDATE users SET last_login_at = now() WHERE id = %s;", (user_id,))
        cur.execute(
            """
            SELECT id AS user_id, coalesce(email_raw, email_normalized) AS email, created_at
            FROM users
            WHERE id = %s;
            """,
            (user_id,),
        )
        u = cur.fetchone()

    if not u:
        raise RuntimeError("user disappeared")
    return (
        User(
            user_id=_row_get(u, "user_id", 0),
            email=_row_get(u, "email", 1),
            created_at=_row_get(u, "created_at", 2),
        ),
        session_token,
    )


def revoke_session(conn: psycopg.Connection[Any], *, session_token: str) -> None:
    token_hash = _sha256_hex(session_token)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE user_sessions SET revoked_at = now() WHERE session_token_hash = %s;",
            (token_hash,),
        )


def get_current_user(conn: psycopg.Connection[Any], *, user_id: UUID) -> UserResponse:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id AS user_id, coalesce(email_raw, email_normalized) AS email, created_at "
            "FROM users WHERE id = %s;",
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        raise KeyError("user not found")
    return UserResponse(
        user=User(
            user_id=_row_get(row, "user_id", 0),
            email=_row_get(row, "email", 1),
            created_at=_row_get(row, "created_at", 2),
        )
    )


def get_user_prefs(conn: psycopg.Connection[Any], *, user_id: UUID) -> UserPrefsResponse:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT reading_mode_default, notification_settings
            FROM user_prefs
            WHERE user_id = %s;
            """,
            (user_id,),
        )
        prefs = cur.fetchone()
        if not prefs:
            cur.execute("INSERT INTO user_prefs(user_id) VALUES (%s);", (user_id,))
            reading_mode_default: Literal["intuition", "deep"] = "intuition"
            notification_settings: dict[str, Any] = {}
        else:
            reading_mode_default = prefs["reading_mode_default"]
            notification_settings = _deep_merge_defaults(
                prefs["notification_settings"] or {}, _DEFAULT_NOTIFICATION_SETTINGS
            )

        cur.execute("SELECT topic_id FROM user_topic_follows WHERE user_id = %s;", (user_id,))
        followed_topic_ids = [_row_get(r, "topic_id", 0) for r in cur.fetchall()]

        cur.execute("SELECT entity_id FROM user_entity_follows WHERE user_id = %s;", (user_id,))
        followed_entity_ids = [_row_get(r, "entity_id", 0) for r in cur.fetchall()]

        cur.execute("SELECT source_id FROM user_source_blocks WHERE user_id = %s;", (user_id,))
        blocked_source_ids = [_row_get(r, "source_id", 0) for r in cur.fetchall()]

        cur.execute("SELECT cluster_id FROM user_cluster_saves WHERE user_id = %s;", (user_id,))
        saved_cluster_ids = [_row_get(r, "cluster_id", 0) for r in cur.fetchall()]

        cur.execute("SELECT cluster_id FROM user_cluster_hides WHERE user_id = %s;", (user_id,))
        hidden_cluster_ids = [_row_get(r, "cluster_id", 0) for r in cur.fetchall()]

    notification_settings = _deep_merge_defaults(
        notification_settings, _DEFAULT_NOTIFICATION_SETTINGS
    )
    return UserPrefsResponse(
        prefs=UserPrefs(
            reading_mode_default=reading_mode_default,
            followed_topic_ids=followed_topic_ids,
            followed_entity_ids=followed_entity_ids,
            blocked_source_ids=blocked_source_ids,
            saved_cluster_ids=saved_cluster_ids,
            hidden_cluster_ids=hidden_cluster_ids,
            notification_settings=notification_settings,
        )
    )


def patch_user_prefs(
    conn: psycopg.Connection[Any],
    *,
    user_id: UUID,
    reading_mode_default: str | None,
    notification_settings: dict[str, Any] | None,
) -> UserPrefsResponse:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO user_prefs(user_id) VALUES (%s) ON CONFLICT DO NOTHING;",
            (user_id,),
        )
        if reading_mode_default is not None:
            cur.execute(
                "UPDATE user_prefs SET reading_mode_default = %s WHERE user_id = %s;",
                (reading_mode_default, user_id),
            )
        if notification_settings is not None:
            cur.execute(
                "UPDATE user_prefs SET notification_settings = %s WHERE user_id = %s;",
                (Jsonb(notification_settings), user_id),
            )
    return get_user_prefs(conn, user_id=user_id)


def simple_ok() -> SimpleOkResponse:
    return SimpleOkResponse(status="ok")


def follow_topic(conn: psycopg.Connection[Any], *, user_id: UUID, topic_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO user_topic_follows(user_id, topic_id) "
            "VALUES (%s,%s) ON CONFLICT DO NOTHING;",
            (user_id, topic_id),
        )


def unfollow_topic(conn: psycopg.Connection[Any], *, user_id: UUID, topic_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_topic_follows WHERE user_id = %s AND topic_id = %s;",
            (user_id, topic_id),
        )


def block_source(conn: psycopg.Connection[Any], *, user_id: UUID, source_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO user_source_blocks(user_id, source_id) "
            "VALUES (%s,%s) ON CONFLICT DO NOTHING;",
            (user_id, source_id),
        )


def unblock_source(conn: psycopg.Connection[Any], *, user_id: UUID, source_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_source_blocks WHERE user_id = %s AND source_id = %s;",
            (user_id, source_id),
        )


def save_cluster(conn: psycopg.Connection[Any], *, user_id: UUID, cluster_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO user_cluster_saves(user_id, cluster_id) "
            "VALUES (%s,%s) ON CONFLICT DO NOTHING;",
            (user_id, cluster_id),
        )


def unsave_cluster(conn: psycopg.Connection[Any], *, user_id: UUID, cluster_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_cluster_saves WHERE user_id = %s AND cluster_id = %s;",
            (user_id, cluster_id),
        )


def hide_cluster(conn: psycopg.Connection[Any], *, user_id: UUID, cluster_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO user_cluster_hides(user_id, cluster_id) "
            "VALUES (%s,%s) ON CONFLICT DO NOTHING;",
            (user_id, cluster_id),
        )


def unhide_cluster(conn: psycopg.Connection[Any], *, user_id: UUID, cluster_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_cluster_hides WHERE user_id = %s AND cluster_id = %s;",
            (user_id, cluster_id),
        )


def list_saved_clusters(conn: psycopg.Connection[Any], *, user_id: UUID) -> UserSavesResponse:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              s.created_at AS saved_at,
              c.id AS cluster_id,
              c.canonical_title,
              c.updated_at,
              c.distinct_source_count,
              c.takeaway,
              c.method_badges,
              c.deep_dive_skip_reason,
              c.anti_hype_flags,
              c.high_impact_label,
              c.high_impact_reasons,
              (
                SELECT array_agg(DISTINCT i.content_type)
                FROM cluster_items ci
                JOIN items i ON i.id = ci.item_id
                WHERE ci.cluster_id = c.id
              ) AS content_type_badges
            FROM user_cluster_saves s
            JOIN story_clusters c ON c.id = s.cluster_id
            WHERE s.user_id = %s AND c.status = 'active'
            ORDER BY s.created_at DESC
            LIMIT 200;
            """,
            (user_id,),
        )
        rows = cur.fetchall()

    cards = _cluster_cards_from_rows(conn, rows)
    card_by_id: dict[UUID, ClusterCard] = {c.cluster_id: c for c in cards}
    saved: list[SavedCluster] = []
    for r in rows:
        saved.append(SavedCluster(saved_at=r["saved_at"], cluster=card_by_id[r["cluster_id"]]))
    return UserSavesResponse(saved=saved)


def for_you_feed(
    conn: psycopg.Connection[Any],
    *,
    user_id: UUID,
    page: int,
    page_size: int,
) -> ClustersFeedResponse:
    offset = (page - 1) * page_size
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              c.id AS cluster_id,
              c.canonical_title,
              c.updated_at,
              c.distinct_source_count,
              c.takeaway,
              c.method_badges,
              c.deep_dive_skip_reason,
              c.anti_hype_flags,
              c.high_impact_label,
              c.high_impact_reasons,
              (
                SELECT array_agg(DISTINCT i.content_type)
                FROM cluster_items ci
                JOIN items i ON i.id = ci.item_id
                WHERE ci.cluster_id = c.id
              ) AS content_type_badges
            FROM story_clusters c
            WHERE c.status = 'active'
              AND NOT EXISTS (
                SELECT 1 FROM user_cluster_hides h WHERE h.user_id = %s AND h.cluster_id = c.id
              )
              AND (
                EXISTS (
                  SELECT 1
                  FROM user_topic_follows f
                  WHERE f.user_id = %s
                    AND EXISTS (
                      SELECT 1
                      FROM cluster_topics ct
                      WHERE ct.cluster_id = c.id
                        AND (
                          ct.topic_id = f.topic_id
                          OR ct.topic_id IN (
                            SELECT id FROM topics WHERE parent_topic_id = f.topic_id
                          )
                        )
                    )
                )
                OR EXISTS (
                  SELECT 1 FROM user_cluster_saves s WHERE s.user_id = %s AND s.cluster_id = c.id
                )
              )
            ORDER BY c.updated_at DESC
            LIMIT %s OFFSET %s;
            """,
            (user_id, user_id, user_id, page_size, offset),
        )
        rows = cur.fetchall()

    cards = _cluster_cards_from_rows(conn, rows)

    # Overlays
    cluster_ids = [c.cluster_id for c in cards]
    saved_set: set[UUID] = set()
    if cluster_ids:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cluster_id FROM user_cluster_saves "
                "WHERE user_id = %s AND cluster_id = ANY(%s);",
                (user_id, cluster_ids),
            )
            saved_set = {_row_get(r, "cluster_id", 0) for r in cur.fetchall()}
    cards2: list[ClusterCard] = []
    for c in cards:
        c2 = c.model_copy()
        c2.is_saved = c.cluster_id in saved_set
        c2.why_in_feed = WhyInFeed(reason="followed_topic_or_saved", details=None)
        cards2.append(c2)

    return ClustersFeedResponse(tab="for_you", page=page, results=cards2)
