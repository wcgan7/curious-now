from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

from curious_now.email_service import EmailMessage, get_email_sender
from curious_now.settings import get_settings

DigestFrequency = Literal["off", "daily", "weekly"]


@dataclass(frozen=True)
class NotificationSettings:
    email_enabled: bool
    story_update_alerts_enabled: bool
    topic_digest_frequency: DigestFrequency
    timezone: str
    quiet_start: time
    quiet_end: time
    max_story_update_emails_per_day: int


def _row_get(row: Any, key: str, idx: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[idx]


def _parse_hhmm(value: str, *, fallback: str) -> time:
    candidates = [str(value or "").strip(), str(fallback or "").strip()]
    for raw in candidates:
        parts = raw.split(":")
        if len(parts) != 2:
            continue
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except (TypeError, ValueError):
            continue
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour=hour, minute=minute)
    return time(0, 0)


def _get_nested(raw: dict[str, Any], path: list[str], default: Any) -> Any:
    cur: Any = raw
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def parse_notification_settings(raw: dict[str, Any] | None) -> NotificationSettings:
    settings = get_settings()
    payload = raw or {}

    email_enabled = bool(_get_nested(payload, ["email", "enabled"], False))
    story_update_alerts_enabled = bool(
        _get_nested(payload, ["email", "story_update_alerts_enabled"], False)
    )
    tdf = _get_nested(payload, ["email", "topic_digest_frequency"], "off")
    topic_digest_frequency: DigestFrequency = (
        tdf if tdf in ("off", "daily", "weekly") else "off"
    )

    timezone_name = str(payload.get("timezone") or settings.default_timezone)
    quiet_hours_raw = payload.get("quiet_hours")
    quiet_hours: dict[str, Any] = quiet_hours_raw if isinstance(quiet_hours_raw, dict) else {}
    quiet_start = _parse_hhmm(
        str(quiet_hours.get("start") or ""),
        fallback=settings.default_quiet_hours_start,
    )
    quiet_end = _parse_hhmm(
        str(quiet_hours.get("end") or ""),
        fallback=settings.default_quiet_hours_end,
    )

    limits_raw = payload.get("limits")
    limits: dict[str, Any] = limits_raw if isinstance(limits_raw, dict) else {}
    max_per_day_raw = limits.get("max_story_update_emails_per_day", 5)
    try:
        max_per_day = int(max_per_day_raw)
    except (TypeError, ValueError):
        max_per_day = 5
    if max_per_day <= 0:
        max_per_day = 5

    return NotificationSettings(
        email_enabled=email_enabled,
        story_update_alerts_enabled=story_update_alerts_enabled,
        topic_digest_frequency=topic_digest_frequency,
        timezone=timezone_name,
        quiet_start=quiet_start,
        quiet_end=quiet_end,
        max_story_update_emails_per_day=max_per_day,
    )


def _normalize_json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _in_quiet_hours(local_t: time, *, start: time, end: time) -> bool:
    if start == end:
        return False
    if start < end:
        return start <= local_t < end
    # Overnight window (e.g. 22:00–08:00)
    return local_t >= start or local_t < end


def _next_quiet_end_local(local_dt: datetime, *, start: time, end: time) -> datetime:
    if not _in_quiet_hours(local_dt.timetz().replace(tzinfo=None), start=start, end=end):
        return local_dt

    d = local_dt.date()
    local_t = local_dt.timetz().replace(tzinfo=None)
    if start < end:
        # Quiet window is within the same day.
        return datetime.combine(d, end, tzinfo=local_dt.tzinfo)

    # Overnight quiet window.
    if local_t < end:
        # Early morning, quiet ends today.
        return datetime.combine(d, end, tzinfo=local_dt.tzinfo)
    # Late evening, quiet ends tomorrow.
    return datetime.combine(d + timedelta(days=1), end, tzinfo=local_dt.tzinfo)


def schedule_outside_quiet_hours(
    *,
    now_utc: datetime,
    tz: ZoneInfo,
    quiet_start: time,
    quiet_end: time,
    prefer_local_time: time | None = None,
) -> datetime:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    local_now = now_utc.astimezone(tz)
    if prefer_local_time is not None:
        # Schedule at a specific local time on the local "today", unless it's already past.
        candidate = datetime.combine(local_now.date(), prefer_local_time, tzinfo=tz)
        if candidate < local_now:
            candidate = candidate + timedelta(days=1)
        local_now = candidate

    scheduled_local = _next_quiet_end_local(local_now, start=quiet_start, end=quiet_end)
    return scheduled_local.astimezone(timezone.utc)


def enqueue_cluster_update_jobs(
    conn: psycopg.Connection[Any],
    *,
    since_utc: datetime | None = None,
    now_utc: datetime | None = None,
) -> int:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    since = since_utc or (now - timedelta(days=7))
    if since.tzinfo is None:
        raise ValueError("since_utc must be timezone-aware")

    # Pull candidate updates + watcher + per-user prefs in one query.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              u.id AS user_id,
              coalesce(u.email_raw, u.email_normalized) AS email,
              p.notification_settings,
              e.id AS update_log_entry_id,
              e.cluster_id,
              e.created_at AS update_created_at
            FROM update_log_entries e
            JOIN user_cluster_watches w ON w.cluster_id = e.cluster_id
            JOIN users u ON u.id = w.user_id
            LEFT JOIN user_prefs p ON p.user_id = u.id
            WHERE e.created_at >= %s;
            """,
            (since,),
        )
        rows = cur.fetchall()

    inserted = 0
    per_user_day_counts: dict[tuple[UUID, date], int] = {}

    for r in rows:
        user_id = UUID(str(_row_get(r, "user_id", 0)))
        raw_settings = _normalize_json_object(_row_get(r, "notification_settings", 2))
        ns = parse_notification_settings(raw_settings)
        if not (ns.email_enabled and ns.story_update_alerts_enabled):
            continue

        try:
            tz = ZoneInfo(ns.timezone)
        except Exception:
            tz = ZoneInfo(get_settings().default_timezone)

        scheduled_for = schedule_outside_quiet_hours(
            now_utc=now,
            tz=tz,
            quiet_start=ns.quiet_start,
            quiet_end=ns.quiet_end,
        )

        day_key = (user_id, scheduled_for.date())
        if day_key not in per_user_day_counts:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*)
                    FROM notification_jobs
                    WHERE user_id = %s
                      AND notification_type = 'cluster_update'
                      AND status IN ('queued','sending','sent')
                      AND scheduled_for >= %s
                      AND scheduled_for < %s;
                    """,
                    (
                        user_id,
                        datetime.combine(scheduled_for.date(), time(0, 0), tzinfo=timezone.utc),
                        datetime.combine(
                            scheduled_for.date() + timedelta(days=1),
                            time(0, 0),
                            tzinfo=timezone.utc,
                        ),
                    ),
                )
                row = cur.fetchone()
                per_user_day_counts[day_key] = int(_row_get(row, "count", 0)) if row else 0

        if per_user_day_counts[day_key] >= ns.max_story_update_emails_per_day:
            continue

        update_id = UUID(str(_row_get(r, "update_log_entry_id", 3)))
        cluster_id = UUID(str(_row_get(r, "cluster_id", 4)))
        dedupe_key = f"cluster_update:{user_id}:{update_id}"
        update_created_at = _row_get(r, "update_created_at", 5)
        payload = {
            "cluster_id": str(cluster_id),
            "update_log_entry_id": str(update_id),
            "update_created_at": update_created_at.isoformat() if update_created_at else None,
        }

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notification_jobs(
                  user_id, channel, notification_type, dedupe_key, scheduled_for, payload
                )
                VALUES (%s, 'email', 'cluster_update', %s, %s, %s)
                ON CONFLICT (dedupe_key) DO NOTHING;
                """,
                (user_id, dedupe_key, scheduled_for, Jsonb(payload)),
            )
            if cur.rowcount == 1:
                inserted += 1
                per_user_day_counts[day_key] += 1

    return inserted


def _period_key(now_local: datetime, *, frequency: DigestFrequency) -> str:
    if frequency == "daily":
        return now_local.date().isoformat()
    # weekly
    iso = now_local.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def enqueue_topic_digest_jobs(
    conn: psycopg.Connection[Any],
    *,
    now_utc: datetime | None = None,
) -> int:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              u.id AS user_id,
              coalesce(u.email_raw, u.email_normalized) AS email,
              p.notification_settings
            FROM users u
            LEFT JOIN user_prefs p ON p.user_id = u.id;
            """
        )
        users = cur.fetchall()

    inserted = 0
    for r in users:
        user_id = UUID(str(_row_get(r, "user_id", 0)))
        ns = parse_notification_settings(
            _normalize_json_object(_row_get(r, "notification_settings", 2))
        )
        if not ns.email_enabled:
            continue
        if ns.topic_digest_frequency == "off":
            continue

        try:
            tz = ZoneInfo(ns.timezone)
        except Exception:
            tz = ZoneInfo(get_settings().default_timezone)

        local_now = now.astimezone(tz)
        # Stage 6 default: digests at 08:00 local.
        if local_now.time() < time(8, 0):
            continue
        if ns.topic_digest_frequency == "weekly" and local_now.weekday() != 0:
            continue

        period_key = _period_key(local_now, frequency=ns.topic_digest_frequency)
        dedupe_key = f"topic_digest:{user_id}:{period_key}"

        window_days = 1 if ns.topic_digest_frequency == "daily" else 7
        window_start = now - timedelta(days=window_days)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT topic_id
                FROM user_topic_follows
                WHERE user_id = %s;
                """,
                (user_id,),
            )
            topic_ids = [UUID(str(_row_get(x, "topic_id", 0))) for x in cur.fetchall()]

        if not topic_ids:
            continue

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT
                  c.id AS cluster_id
                FROM cluster_topics ct
                JOIN story_clusters c ON c.id = ct.cluster_id
                WHERE ct.topic_id = ANY(%s)
                  AND c.status = 'active'
                  AND c.updated_at >= %s
                ORDER BY c.updated_at DESC
                LIMIT 20;
                """,
                (topic_ids, window_start),
            )
            cluster_ids = [UUID(str(_row_get(x, "cluster_id", 0))) for x in cur.fetchall()]

        scheduled_for = schedule_outside_quiet_hours(
            now_utc=now,
            tz=tz,
            quiet_start=ns.quiet_start,
            quiet_end=ns.quiet_end,
            prefer_local_time=time(8, 0),
        )

        payload = {
            "topic_ids": [str(tid) for tid in topic_ids],
            "cluster_ids": [str(cid) for cid in cluster_ids],
            "period_key": period_key,
            "period_start_utc": window_start.isoformat(),
            "period_end_utc": now.isoformat(),
        }

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notification_jobs(
                  user_id, channel, notification_type, dedupe_key, scheduled_for, payload
                )
                VALUES (%s, 'email', 'topic_digest', %s, %s, %s)
                ON CONFLICT (dedupe_key) DO NOTHING;
                """,
                (user_id, dedupe_key, scheduled_for, Jsonb(payload)),
            )
            if cur.rowcount == 1:
                inserted += 1

    return inserted


def _render_cluster_update_email(
    conn: psycopg.Connection[Any], *, cluster_id: UUID, update_log_entry_id: UUID
) -> tuple[str, str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.canonical_title
            FROM story_clusters c
            WHERE c.id = %s;
            """,
            (cluster_id,),
        )
        c = cur.fetchone()
        title = str(_row_get(c, "canonical_title", 0)) if c else "Story update"

        cur.execute(
            """
            SELECT summary
            FROM update_log_entries
            WHERE id = %s;
            """,
            (update_log_entry_id,),
        )
        e = cur.fetchone()
        summary = str(_row_get(e, "summary", 0)) if e else ""

    base = get_settings().public_app_base_url.rstrip("/")
    link = f"{base}/clusters/{cluster_id}"

    subject = f"Update: {title}"
    text = f"{title}\n\n{summary}\n\nOpen: {link}\n"
    html = f"<h2>{title}</h2><p>{summary}</p><p><a href=\"{link}\">Open story</a></p>"
    return subject, text, html


def _render_topic_digest_email(
    conn: psycopg.Connection[Any], *, topic_ids: list[UUID], cluster_ids: list[UUID]
) -> tuple[str, str, str]:
    topic_names: list[str] = []
    if topic_ids:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name FROM topics WHERE id = ANY(%s) ORDER BY name ASC;",
                (topic_ids,),
            )
            topic_names = [str(_row_get(r, "name", 0)) for r in cur.fetchall()]

    cluster_titles: list[str] = []
    if cluster_ids:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT canonical_title
                FROM story_clusters
                WHERE id = ANY(%s)
                ORDER BY updated_at DESC;
                """,
                (cluster_ids,),
            )
            cluster_titles = [str(_row_get(r, "canonical_title", 0)) for r in cur.fetchall()]

    subject = "Your topic digest"
    if topic_names:
        subject = f"Digest: {', '.join(topic_names[:3])}" + ("…" if len(topic_names) > 3 else "")

    base = get_settings().public_app_base_url.rstrip("/")
    lines = []
    for title in cluster_titles[:20]:
        lines.append(f"- {title}")
    topics_line = ", ".join(topic_names) if topic_names else ""
    text = f"Topics: {topics_line}\n\nRecent stories:\n" + "\n".join(lines) + "\n"
    html = "<h2>Your topic digest</h2>"
    if topic_names:
        html += f"<p><b>Topics:</b> {topics_line}</p>"
    if cluster_titles:
        html += "<ul>" + "".join(f"<li>{t}</li>" for t in cluster_titles[:20]) + "</ul>"
    html += f"<p><a href=\"{base}/topics\">Browse topics</a></p>"
    return subject, text, html


def send_due_notification_jobs(
    conn: psycopg.Connection[Any],
    *,
    now_utc: datetime | None = None,
    limit: int = 50,
) -> int:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE notification_jobs j
            SET status = 'sending',
                attempts = j.attempts + 1
            WHERE j.id IN (
              SELECT id
              FROM notification_jobs
              WHERE status = 'queued' AND scheduled_for <= %s
              ORDER BY scheduled_for ASC, created_at ASC
              LIMIT %s
            )
            RETURNING j.id, j.user_id, j.notification_type, j.payload;
            """,
            (now, limit),
        )
        jobs = cur.fetchall()

    # Get email sender (configured based on settings)
    email_sender = get_email_sender()
    settings = get_settings()

    sent = 0
    for j in jobs:
        job_id = UUID(str(_row_get(j, "id", 0)))
        user_id = UUID(str(_row_get(j, "user_id", 1)))
        ntype = str(_row_get(j, "notification_type", 2))
        payload = _normalize_json_object(_row_get(j, "payload", 3))

        # Get user email
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT coalesce(email_raw, email_normalized) AS email
                FROM users
                WHERE id = %s;
                """,
                (user_id,),
            )
            user_row = cur.fetchone()

        if not user_row:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE notification_jobs
                    SET status = 'error',
                        last_error = 'User not found'
                    WHERE id = %s;
                    """,
                    (job_id,),
                )
            continue

        user_email = str(_row_get(user_row, "email", 0))
        if not user_email:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE notification_jobs
                    SET status = 'error',
                        last_error = 'User has no email'
                    WHERE id = %s;
                    """,
                    (job_id,),
                )
            continue

        try:
            if ntype == "cluster_update":
                subject, text, html = _render_cluster_update_email(
                    conn,
                    cluster_id=UUID(payload["cluster_id"]),
                    update_log_entry_id=UUID(payload["update_log_entry_id"]),
                )
            elif ntype == "topic_digest":
                subject, text, html = _render_topic_digest_email(
                    conn,
                    topic_ids=[UUID(x) for x in payload.get("topic_ids", [])],
                    cluster_ids=[UUID(x) for x in payload.get("cluster_ids", [])],
                )
            else:
                raise ValueError(f"unsupported notification_type: {ntype}")

            # Send the email using configured email service
            message = EmailMessage(
                to_email=user_email,
                subject=subject,
                text_content=text,
                html_content=html,
                from_email=settings.email_from_address,
                from_name=settings.email_from_name,
                categories=[f"curious_now_{ntype}"],
            )
            result = email_sender.send(message)

            if result.success:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE notification_jobs
                        SET status = 'sent',
                            rendered_subject = %s,
                            rendered_text = %s,
                            rendered_html = %s,
                            sent_at = now()
                        WHERE id = %s;
                        """,
                        (subject, text, html, job_id),
                    )
                sent += 1
            else:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE notification_jobs
                        SET status = 'error',
                            last_error = %s
                        WHERE id = %s;
                        """,
                        (result.error or "Email send failed", job_id),
                    )
        except Exception as exc:  # noqa: BLE001
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE notification_jobs
                    SET status = 'error',
                        last_error = %s
                    WHERE id = %s;
                    """,
                    (str(exc), job_id),
                )

    return sent
