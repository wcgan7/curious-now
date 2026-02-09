"""
Notifications module - stub implementation.

TODO: Implement actual notification functionality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg


def enqueue_cluster_update_jobs(
    conn: "psycopg.Connection[object]",
    *,
    since_days: int = 7,
) -> int:
    """Enqueue notification jobs for updated clusters. Stub - not implemented."""
    # TODO: Implement cluster update notifications
    return 0


def enqueue_topic_digest_jobs(
    conn: "psycopg.Connection[object]",
    *,
    since_days: int = 7,
) -> int:
    """Enqueue topic digest notification jobs. Stub - not implemented."""
    # TODO: Implement topic digest notifications
    return 0


def send_due_notification_jobs(
    conn: "psycopg.Connection[object]",
    *,
    limit: int = 50,
) -> tuple[int, int]:
    """Send pending notification jobs. Stub - not implemented.

    Returns:
        Tuple of (sent_count, failed_count)
    """
    # TODO: Implement notification sending
    return (0, 0)
