#!/usr/bin/env python
"""Re-type stored items against their source's content-type rules.

Rules are applied at ingest, so a rule added today does nothing for what
arrived yesterday. This walks the items already stored and applies them, which
matters because the mislabelled rows are the ones a reader can see now.

    PYTHONPATH=. python scripts/v2_backfill_content_type.py [--apply]

Reports what would change and changes nothing unless `--apply` is given. Only
items still resting on their feed's default are touched: a type established
from the document or the classifier is better evidenced than any pattern and is
left alone.

Items on a feed that has rules but match none of them are marked unmatched
rather than left as a default, because a default on a mixed feed establishes
nothing — which is the difference between arXiv, where every item really is a
preprint, and Nature, where most items are not research at all.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

import psycopg

from curious_now_v2.core.source_registry import ContentTypeRule


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes")
    parser.add_argument(
        "--database-url", default=os.environ.get("CURIOUS_NOW_V2_DATABASE_URL")
    )
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("set CURIOUS_NOW_V2_DATABASE_URL or pass --database-url")

    changes: list[tuple[str, str, str, str, str]] = []
    with psycopg.connect(args.database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            # A rule matches an item's own URL or DOI, so every rule belonging to
            # the item's source can be offered safely: a pattern naming one
            # publisher's identifiers cannot match another's.
            cursor.execute(
                """
                SELECT i.id::text, s.name, i.url, i.doi, i.content_type,
                       (SELECT jsonb_agg(r)
                        FROM source_feeds f, jsonb_array_elements(f.content_type_rules) r
                        WHERE f.source_id = i.source_id)
                FROM items i
                JOIN sources s ON s.id = i.source_id
                WHERE i.content_type_basis = 'feed_default';
                """
            )
            rows = cursor.fetchall()

        unmatched: list[str] = []
        for item_id, source, url, doi, current, raw_rules in rows:
            rules = [ContentTypeRule.model_validate(raw) for raw in raw_rules or []]
            matched = next((r for r in rules if r.matches(url, doi)), None)
            if matched is not None:
                changes.append(
                    (item_id, source, current, matched.content_type.value,
                     matched.note or f"matched {matched.pattern!r}")
                )
            elif rules:
                unmatched.append(item_id)

        tally = Counter((s, c, n) for _, s, c, n, _ in changes)
        for (source, before, after), count in sorted(tally.items()):
            arrow = "unchanged" if before == after else f"{before} -> {after}"
            print(f"  {count:5d}  {source[:28]:28s} {arrow}")

        moved = sum(n for (_, b, a), n in tally.items() if b != a)
        print(f"\n{len(rows):,} items rest on a feed default; "
              f"{len(changes):,} match a rule, {moved:,} change type, "
              f"{len(unmatched):,} on a mixed feed match nothing")

        if not args.apply:
            print("dry run; pass --apply to write")
            return 0

        with connection.cursor() as cursor:
            cursor.executemany(
                """
                UPDATE items SET
                  content_type = %s,
                  content_type_basis = 'source_pattern',
                  content_type_note = %s,
                  updated_at = now()
                WHERE id = %s AND content_type_basis = 'feed_default';
                """,
                [(after, note, item_id) for item_id, _, _, after, note in changes],
            )
            # A default reached on a mixed feed establishes nothing about the
            # item, and must not be read as though it had.
            cursor.executemany(
                """
                UPDATE items SET
                  content_type_basis = 'feed_unmatched',
                  content_type_note = %s,
                  updated_at = now()
                WHERE id = %s AND content_type_basis = 'feed_default';
                """,
                [
                    ("no rule matched; the feed default is a fallback here", item_id)
                    for item_id in unmatched
                ],
            )
        print(f"applied to {len(changes):,} items, "
              f"{len(unmatched):,} marked unmatched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
