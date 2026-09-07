#!/usr/bin/env python
"""Retire stored items that the current source config would never accept.

Config decides what is ingested next time; it says nothing about what was
ingested already. Deactivating OpenAI stops its feed being polled, and the
thousand items it left behind sit in the retrieval queue regardless. Excluding
the BBC's radio schedule stops the next one arriving, not the four here now.

    PYTHONPATH=. python scripts/v2_retire_items.py [--apply]

Retires, rather than deletes. An item marked blocked leaves the queues and its
story leaves the feed, while the row stays readable — a source may be dropped
for being unfetchable today and become worth reading later, and the decision
should not need the data back to be reversed. Reports and changes nothing
unless `--apply` is given.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

from curious_now_v2.core.source_registry import SourceRegistry

CONFIG = Path(__file__).parents[1] / "config" / "v2" / "sources.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument(
        "--database-url", default=os.environ.get("CURIOUS_NOW_V2_DATABASE_URL")
    )
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("set CURIOUS_NOW_V2_DATABASE_URL or pass --database-url")

    registry = SourceRegistry.model_validate(json.loads(args.config.read_text()))
    inactive = [source.name for source in registry.sources if not source.active]
    excluded = {
        source.name: [p for feed in source.feeds for p in feed.exclude_patterns]
        for source in registry.sources
        if any(feed.exclude_patterns for feed in source.feeds)
    }

    with psycopg.connect(args.database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            for name in inactive:
                cursor.execute(
                    """
                    SELECT count(*) FILTER (WHERE i.full_text_status <> 'blocked'),
                           count(*) FILTER (WHERE st.status = 'published')
                    FROM items i
                    JOIN sources s ON s.id = i.source_id
                    LEFT JOIN story_items si ON si.item_id = i.id
                    LEFT JOIN stories st ON st.id = si.story_id
                    WHERE s.name = %s;
                    """,
                    (name,),
                )
                queued, published = cursor.fetchone() or (0, 0)
                print(f"  {name:26s} inactive: {queued:,} items still queued, "
                      f"{published:,} published stories to withdraw")

            for name, patterns in excluded.items():
                for pattern in patterns:
                    cursor.execute(
                        """
                        SELECT count(*) FROM items i
                        JOIN sources s ON s.id = i.source_id
                        WHERE s.name = %s AND i.url LIKE %s
                          AND i.full_text_status <> 'blocked';
                        """,
                        (name, f"%{pattern}%"),
                    )
                    count = (cursor.fetchone() or (0,))[0]
                    print(f"  {name:26s} excludes {pattern:16s} {count:,} items")

        if not args.apply:
            print("\ndry run; pass --apply to write")
            return 0

        with connection.transaction(), connection.cursor() as cursor:
            # Leaving the queues is what retirement means: blocked is already
            # the status for "asked and refused", and it is excluded from the
            # retry window that not_found and error sit inside.
            cursor.execute(
                """
                UPDATE items SET
                  full_text_status = 'blocked',
                  full_text_error = %s,
                  updated_at = now()
                WHERE source_id IN (SELECT id FROM sources WHERE NOT active)
                  AND full_text_status <> 'blocked';
                """,
                ("retired: source is no longer active",),
            )
            retired = cursor.rowcount

            for name, patterns in excluded.items():
                for pattern in patterns:
                    cursor.execute(
                        """
                        UPDATE items SET
                          full_text_status = 'blocked',
                          full_text_error = %s,
                          updated_at = now()
                        WHERE source_id = (SELECT id FROM sources WHERE name = %s)
                          AND url LIKE %s
                          AND full_text_status <> 'blocked';
                        """,
                        (f"retired: {pattern} is not a readable item", name, f"%{pattern}%"),
                    )
                    retired += cursor.rowcount

            # A story whose only evidence has been retired has nothing behind
            # it, so it leaves both the reader and the generation queue rather
            # than standing on text retained by a blocked item.
            cursor.execute(
                """
                UPDATE stories SET
                  status = 'draft',
                  supported_depths = '{}',
                  publication_reasons = %s,
                  updated_at = now()
                WHERE status <> 'hidden'
                  AND NOT EXISTS (
                    SELECT 1 FROM story_items si
                    JOIN items i ON i.id = si.item_id
                    WHERE si.story_id = stories.id
                      AND i.full_text_status <> 'blocked'
                  );
                """,
                (psycopg.types.json.Jsonb(["withdrawn: every source item was retired"]),),
            )
            withdrawn = cursor.rowcount

        print(f"\nretired {retired:,} items, withdrew {withdrawn:,} stories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
