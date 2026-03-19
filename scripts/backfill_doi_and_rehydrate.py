#!/usr/bin/env python3
"""One-off backfill script to fix items affected by the hydration bugs.

1. Backfill DOIs from snippet text for items where doi IS NULL.
2. Reset hydration for landing_page items whose text fails quality checks
   after the script/style regex fix, so they get re-hydrated on next sync.

Usage:
    python scripts/backfill_doi_and_rehydrate.py [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import re
from psycopg.rows import dict_row

from curious_now.db import DB
from curious_now.paper_text_hydration import (
    _clean_full_text,
    _is_fulltext_quality_sufficient,
)
from curious_now.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger("backfill_doi_rehyd")

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _extract_doi(text: str) -> str | None:
    m = _DOI_RE.search(text)
    if not m:
        return None
    return _CAMEL_SPLIT_RE.split(m.group(0))[0].rstrip("-_./") or None


def backfill_dois(db: DB, *, dry_run: bool) -> int:
    """Find items with doi=NULL but a DOI in the snippet, and update them."""
    with db.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, title, url, snippet
                FROM items
                WHERE doi IS NULL
                  AND snippet IS NOT NULL
                  AND btrim(snippet) != ''
            """)
            rows = cur.fetchall()

        logger.info("Found %d items with doi=NULL and non-empty snippet", len(rows))
        updated = 0
        for row in rows:
            doi = _extract_doi(row["snippet"])
            if not doi:
                continue
            logger.info("  %s: extracted doi=%s from snippet", row["id"], doi)
            if not dry_run:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE items SET doi = %s, updated_at = now() WHERE id = %s AND doi IS NULL",
                        (doi, row["id"]),
                    )
                conn.commit()
            updated += 1

        logger.info("DOI backfill: %d items %s",
                     updated, "would be updated" if dry_run else "updated")
        return updated


def reset_bad_landing_page_hydrations(db: DB, *, dry_run: bool) -> int:
    """Reset hydration for landing_page items whose text is now rejected by quality checks."""
    with db.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, full_text, url
                FROM items
                WHERE full_text_source = 'landing_page'
                  AND full_text IS NOT NULL
                  AND btrim(full_text) != ''
            """)
            rows = cur.fetchall()

        logger.info("Found %d items hydrated via landing_page", len(rows))
        reset_count = 0
        for row in rows:
            # Re-clean with the fixed regex and check quality
            cleaned = _clean_full_text(row["full_text"])
            if cleaned and _is_fulltext_quality_sufficient(cleaned):
                continue  # still good after the fix

            logger.info("  %s: text fails quality after re-clean (%s), resetting",
                        row["id"], row["url"])
            if not dry_run:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE items
                        SET full_text = NULL,
                            full_text_status = 'pending',
                            full_text_source = NULL,
                            full_text_kind = NULL,
                            full_text_license = NULL,
                            full_text_error = NULL,
                            full_text_fetched_at = NULL,
                            updated_at = now()
                        WHERE id = %s
                    """, (row["id"],))
                conn.commit()
            reset_count += 1

        logger.info("Hydration reset: %d items %s",
                     reset_count, "would be reset" if dry_run else "reset")
        return reset_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without modifying the database")
    args = parser.parse_args()

    settings = get_settings()
    db = DB(dsn=settings.database_url)

    logger.info("=== Step 1: Backfill DOIs from snippets ===")
    doi_count = backfill_dois(db, dry_run=args.dry_run)

    logger.info("=== Step 2: Reset bad landing_page hydrations ===")
    reset_count = reset_bad_landing_page_hydrations(db, dry_run=args.dry_run)

    logger.info("=== Done: %d DOIs backfilled, %d hydrations reset ===",
                doi_count, reset_count)
    if args.dry_run:
        logger.info("(dry-run mode — no changes were made)")


if __name__ == "__main__":
    main()
