from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg


def purge_logs(
    conn: psycopg.Connection[Any],
    *,
    now_utc: datetime | None = None,
    keep_days: int = 90,
    dry_run: bool = True,
) -> dict[str, int]:
    now = now_utc or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=keep_days)

    def count(sql: str, params: tuple[Any, ...]) -> int:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        if not row:
            return 0
        return int(row[0] if not isinstance(row, dict) else list(row.values())[0])

    def delete(sql: str, params: tuple[Any, ...]) -> int:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.rowcount)

    out: dict[str, int] = {}

    for name, table, col in [
        ("engagement_events", "engagement_events", "created_at"),
        ("feed_fetch_logs", "feed_fetch_logs", "created_at"),
    ]:
        if dry_run:
            out[name] = count(f"SELECT count(*) FROM {table} WHERE {col} < %s;", (cutoff,))
        else:
            out[name] = delete(f"DELETE FROM {table} WHERE {col} < %s;", (cutoff,))

    # notification_jobs: purge only after sent
    if dry_run:
        out["notification_jobs"] = count(
            "SELECT count(*) FROM notification_jobs WHERE sent_at IS NOT NULL AND sent_at < %s;",
            (cutoff,),
        )
    else:
        out["notification_jobs"] = delete(
            "DELETE FROM notification_jobs WHERE sent_at IS NOT NULL AND sent_at < %s;",
            (cutoff,),
        )

    return out

