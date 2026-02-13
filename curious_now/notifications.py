from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

_DEFAULT_TIMEZONE = "UTC"
_DEFAULT_QUIET_START = "22:00"
_DEFAULT_QUIET_END = "08:00"
_DEFAULT_DAILY_LIMIT = 5


@dataclass(frozen=True)
class _UserNotificationPrefs:
    email_enabled: bool
    story_update_alerts_enabled: bool
    topic_digest_frequency: str
    timezone_name: str
    quiet_start: time
    quiet_end: time
    max_story_update_emails_per_day: int


def _row_get(row: Any, key: str, idx: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[idx]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "1", "yes", "on"}:
            return True
        if low in {"false", "0", "no", "off"}:
            return False
    return default


def _to_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _parse_hhmm(value: Any, default: str) -> time:
    raw = str(value) if value is not None else default
    try:
        hh_raw, mm_raw = raw.split(":", 1)
        hh = int(hh_raw)
        mm = int(mm_raw)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return time(hour=hh, minute=mm)
    except (TypeError, ValueError):
        pass
    hh_default, mm_default = default.split(":", 1)
    return time(hour=int(hh_default), minute=int(mm_default))


def _user_prefs_from_notification_settings(raw_settings: Any) -> _UserNotificationPrefs:
    settings = _as_dict(raw_settings)
    email = _as_dict(settings.get("email"))
    quiet = _as_dict(settings.get("quiet_hours"))
    limits = _as_dict(settings.get("limits"))

    frequency_raw = str(email.get("topic_digest_frequency", "off")).lower().strip()
    if frequency_raw not in {"off", "daily", "weekly"}:
        frequency_raw = "off"

    timezone_name = str(settings.get("timezone") or _DEFAULT_TIMEZONE).strip() or _DEFAULT_TIMEZONE
    try:
        ZoneInfo(timezone_name)
    except Exception:
        timezone_name = _DEFAULT_TIMEZONE

    return _UserNotificationPrefs(
        email_enabled=_to_bool(email.get("enabled"), default=False),
        story_update_alerts_enabled=_to_bool(email.get("story_update_alerts_enabled"), default=False),
        topic_digest_frequency=frequency_raw,
        timezone_name=timezone_name,
        quiet_start=_parse_hhmm(quiet.get("start"), _DEFAULT_QUIET_START),
        quiet_end=_parse_hhmm(quiet.get("end"), _DEFAULT_QUIET_END),
        max_story_update_emails_per_day=_to_int(
            limits.get("max_story_update_emails_per_day"),
            _DEFAULT_DAILY_LIMIT,
        ),
    )


def _is_within_quiet_hours(local_time: time, quiet_start: time, quiet_end: time) -> bool:
    if quiet_start == quiet_end:
        return False
    if quiet_start < quiet_end:
        return quiet_start <= local_time < quiet_end
    return local_time >= quiet_start or local_time < quiet_end


def _next_quiet_end(now_utc: datetime, *, quiet_start: time, quiet_end: time, tz: ZoneInfo) -> datetime:
    local_now = now_utc.astimezone(tz)
    local_date = local_now.date()
    local_time = local_now.timetz().replace(tzinfo=None)
    scheduled_date = local_date

    if quiet_start < quiet_end:
        if local_time >= quiet_end:
            scheduled_date = local_date + timedelta(days=1)
    else:
        if local_time >= quiet_start:
            scheduled_date = local_date + timedelta(days=1)

    scheduled_local = datetime.combine(scheduled_date, quiet_end, tzinfo=tz)
    return scheduled_local.astimezone(timezone.utc)


def _resolve_scheduled_for(now_utc: datetime, prefs: _UserNotificationPrefs) -> datetime:
    tz = ZoneInfo(prefs.timezone_name)
    local_now = now_utc.astimezone(tz)
    local_time = local_now.timetz().replace(tzinfo=None)
    if not _is_within_quiet_hours(local_time, prefs.quiet_start, prefs.quiet_end):
        return now_utc
    return _next_quiet_end(
        now_utc,
        quiet_start=prefs.quiet_start,
        quiet_end=prefs.quiet_end,
        tz=tz,
    )


def _local_day_bounds_utc(local_day: date, timezone_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone_name)
    start_local = datetime.combine(local_day, time(hour=0, minute=0), tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _count_user_story_update_jobs(
    conn: psycopg.Connection[Any],
    *,
    user_id: UUID,
    local_day: date,
    timezone_name: str,
) -> int:
    start_utc, end_utc = _local_day_bounds_utc(local_day, timezone_name)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM notification_jobs
            WHERE user_id = %s
              AND notification_type = 'cluster_update'
              AND status IN ('queued', 'sending', 'sent')
              AND scheduled_for >= %s
              AND scheduled_for < %s;
            """,
            (user_id, start_utc, end_utc),
        )
        row = cur.fetchone()
    if not row:
        return 0
    return int(_row_get(row, "count", 0))


def _insert_notification_job(
    conn: psycopg.Connection[Any],
    *,
    user_id: UUID,
    notification_type: str,
    dedupe_key: str,
    scheduled_for: datetime,
    payload: dict[str, Any],
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS(
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = 'notification_jobs'
                AND column_name = 'channel'
            );
            """
        )
        row = cur.fetchone()
    has_channel = bool(row and _row_get(row, "exists", 0))

    with conn.cursor() as cur:
        if has_channel:
            cur.execute(
                """
                INSERT INTO notification_jobs(
                  user_id, channel, notification_type, status, dedupe_key, scheduled_for, payload
                )
                VALUES (%s, %s, %s, 'queued', %s, %s, %s)
                ON CONFLICT (dedupe_key) DO NOTHING;
                """,
                (user_id, "email", notification_type, dedupe_key, scheduled_for, Jsonb(payload)),
            )
        else:
            cur.execute(
                """
                INSERT INTO notification_jobs(
                  user_id, notification_type, status, dedupe_key, scheduled_for, payload
                )
                VALUES (%s, %s, 'queued', %s, %s, %s)
                ON CONFLICT (dedupe_key) DO NOTHING;
                """,
                (user_id, notification_type, dedupe_key, scheduled_for, Jsonb(payload)),
            )
        return int(cur.rowcount)


def enqueue_cluster_update_jobs(
    conn: psycopg.Connection[Any],
    *,
    since_utc: datetime | None = None,
    now_utc: datetime | None = None,
    since_days: int = 7,
) -> int:
    now = now_utc or datetime.now(timezone.utc)
    window_start = since_utc or (now - timedelta(days=since_days))

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              ule.id AS update_log_entry_id,
              ule.cluster_id,
              w.user_id,
              up.notification_settings
            FROM update_log_entries ule
            JOIN user_cluster_watches w
              ON w.cluster_id = ule.cluster_id
            LEFT JOIN user_prefs up
              ON up.user_id = w.user_id
            WHERE ule.created_at >= %s
              AND ule.created_at <= %s
            ORDER BY ule.created_at ASC, w.user_id ASC;
            """,
            (window_start, now),
        )
        rows = cur.fetchall()

    inserted = 0
    daily_count_cache: dict[tuple[UUID, str], int] = {}

    for row in rows:
        update_log_entry_id = UUID(str(_row_get(row, "update_log_entry_id", 0)))
        cluster_id = UUID(str(_row_get(row, "cluster_id", 1)))
        user_id = UUID(str(_row_get(row, "user_id", 2)))
        prefs = _user_prefs_from_notification_settings(_row_get(row, "notification_settings", 3))

        if not prefs.email_enabled or not prefs.story_update_alerts_enabled:
            continue

        scheduled_for = _resolve_scheduled_for(now, prefs)
        local_day = scheduled_for.astimezone(ZoneInfo(prefs.timezone_name)).date()
        cache_key = (user_id, local_day.isoformat())
        if cache_key not in daily_count_cache:
            daily_count_cache[cache_key] = _count_user_story_update_jobs(
                conn,
                user_id=user_id,
                local_day=local_day,
                timezone_name=prefs.timezone_name,
            )

        if daily_count_cache[cache_key] >= prefs.max_story_update_emails_per_day:
            continue

        dedupe_key = f"cluster_update:{user_id}:{update_log_entry_id}"
        payload = {
            "cluster_id": str(cluster_id),
            "update_log_entry_id": str(update_log_entry_id),
        }
        delta = _insert_notification_job(
            conn,
            user_id=user_id,
            notification_type="cluster_update",
            dedupe_key=dedupe_key,
            scheduled_for=scheduled_for,
            payload=payload,
        )
        inserted += delta
        if delta:
            daily_count_cache[cache_key] += 1

    return inserted


def _digest_period_bounds(
    now: datetime,
    *,
    frequency: str,
    timezone_name: str,
) -> tuple[str, datetime, datetime] | None:
    tz = ZoneInfo(timezone_name)
    local_now = now.astimezone(tz)

    if frequency == "daily":
        due_local = local_now.replace(hour=8, minute=0, second=0, microsecond=0)
        if local_now < due_local:
            return None
        period_end = due_local
        period_start = period_end - timedelta(days=1)
        period_key = period_end.strftime("%Y-%m-%d")
        return (period_key, period_start.astimezone(timezone.utc), period_end.astimezone(timezone.utc))

    if frequency == "weekly":
        monday_start = (local_now - timedelta(days=local_now.weekday())).replace(
            hour=8,
            minute=0,
            second=0,
            microsecond=0,
        )
        if local_now < monday_start:
            monday_start -= timedelta(days=7)
        period_end = monday_start
        period_start = period_end - timedelta(days=7)
        period_key = period_end.strftime("%G-W%V")
        return (period_key, period_start.astimezone(timezone.utc), period_end.astimezone(timezone.utc))

    return None


def enqueue_topic_digest_jobs(
    conn: psycopg.Connection[Any],
    *,
    since_utc: datetime | None = None,
    now_utc: datetime | None = None,
    since_days: int = 7,
) -> int:
    del since_utc  # currently derived from per-user digest cadence
    del since_days
    now = now_utc or datetime.now(timezone.utc)

    with conn.cursor() as cur:
        cur.execute("SELECT user_id, notification_settings FROM user_prefs;")
        user_rows = cur.fetchall()

    inserted = 0
    for row in user_rows:
        user_id = UUID(str(_row_get(row, "user_id", 0)))
        prefs = _user_prefs_from_notification_settings(_row_get(row, "notification_settings", 1))

        if not prefs.email_enabled or prefs.topic_digest_frequency == "off":
            continue

        period = _digest_period_bounds(
            now,
            frequency=prefs.topic_digest_frequency,
            timezone_name=prefs.timezone_name,
        )
        if period is None:
            continue

        period_key, period_start_utc, period_end_utc = period
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT topic_id
                FROM user_topic_follows
                WHERE user_id = %s
                ORDER BY topic_id;
                """,
                (user_id,),
            )
            topic_rows = cur.fetchall()
        topic_ids = [UUID(str(_row_get(r, "topic_id", 0))) for r in topic_rows]
        if not topic_ids:
            continue

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ct.cluster_id
                FROM cluster_topics ct
                JOIN story_clusters sc ON sc.id = ct.cluster_id
                WHERE ct.topic_id = ANY(%s)
                  AND sc.status = 'active'
                  AND sc.updated_at >= %s
                  AND sc.updated_at < %s
                ORDER BY ct.cluster_id
                LIMIT 50;
                """,
                (topic_ids, period_start_utc, period_end_utc),
            )
            cluster_rows = cur.fetchall()
        cluster_ids = [UUID(str(_row_get(r, "cluster_id", 0))) for r in cluster_rows]
        if not cluster_ids:
            continue

        scheduled_for = _resolve_scheduled_for(now, prefs)
        dedupe_key = f"topic_digest:{user_id}:{period_key}"
        payload = {
            "topic_ids": [str(tid) for tid in topic_ids],
            "cluster_ids": [str(cid) for cid in cluster_ids],
            "period_key": period_key,
            "period_start": period_start_utc.isoformat(),
            "period_end": period_end_utc.isoformat(),
        }
        inserted += _insert_notification_job(
            conn,
            user_id=user_id,
            notification_type="topic_digest",
            dedupe_key=dedupe_key,
            scheduled_for=scheduled_for,
            payload=payload,
        )

    return inserted


def send_due_notification_jobs(
    conn: psycopg.Connection[Any],
    *,
    now_utc: datetime | None = None,
    limit: int = 50,
) -> int:
    now = now_utc or datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM notification_jobs
            WHERE status = 'queued'
              AND scheduled_for <= %s
            ORDER BY scheduled_for ASC
            LIMIT %s;
            """,
            (now, int(limit)),
        )
        rows = cur.fetchall()

    sent = 0
    for row in rows:
        job_id = _row_get(row, "id", 0)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE notification_jobs
                SET status = 'sent', sent_at = %s
                WHERE id = %s
                  AND status = 'queued';
                """,
                (now, job_id),
            )
            sent += int(cur.rowcount)
    return sent
