#!/usr/bin/env python
"""Recover author lists for papers hydrated before anyone kept them.

Hydration has always fetched the response that carries them and stored only the
abstract, so 6,799 papers know nothing about who wrote them. The corpus cites
Fei-Fei Li 82 times across 72 papers and cannot say so, which is the whole
reason a source we should have been watching had to arrive by tweet.

This costs API time and no model spend. It re-asks arXiv in batches of 50 and
Crossref one DOI at a time, both of which the normal hydration run already does
on a schedule; the only new thing is that it selects papers that already have
an abstract.

Resumable and idempotent. Every attempt stamps `authors_attempted_at`, and
selection is on its absence -- so a paper whose provider genuinely lists no
authors is not re-fetched forever, which `NOT EXISTS (paper_authors)` alone
could not distinguish from one never tried.

Crossref asks that heavy callers identify themselves for its polite pool, which
is a real difference in service rather than a formality. Pass --mailto or set
CURIOUS_NOW_CONTACT_EMAIL.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.db.hydration import (
    ARXIV_DELAY_SECONDS,
    USER_AGENT,
    store_authors,
)
from curious_now_v2.pipeline.hydrate import (
    ARXIV_API,
    ARXIV_BATCH_SIZE,
    CROSSREF_API,
    Author,
    arxiv_batches,
    parse_arxiv_authors,
    parse_crossref_authors,
)

# Crossref is one request per DOI and asks for a steady, identified caller
# rather than a burst.
CROSSREF_DELAY_SECONDS = 0.2


def select_papers(
    connection: psycopg.Connection[Any],
    *,
    limit: int,
) -> tuple[list[tuple[UUID, str]], list[tuple[UUID, str]]]:
    """Papers with an identifier that have never been asked for authors.

    The two pools are given half the run each, for the reason
    `list_papers_needing_abstracts` splits them: 3,393 papers carry an arXiv ID
    and 1,540 a DOI alone, so filling the window in creation order would mean
    Crossref went unasked until arXiv was exhausted -- and Crossref holds the
    ORCIDs, which are the only part of this worth joining on later.
    """

    def select(condition: str, column: str, count: int) -> list[tuple[UUID, str]]:
        if count < 1:
            return []
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, {column}
                FROM papers
                WHERE {condition}
                  AND metadata->>'authors_attempted_at' IS NULL
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (count,),
            )
            return [(row[0], row[1]) for row in cursor]

    half = max(limit // 2, 1)
    arxiv = select("arxiv_id IS NOT NULL", "arxiv_id", half)
    doi_only = select(
        "arxiv_id IS NULL AND doi IS NOT NULL", "doi", limit - len(arxiv)
    )
    # Let whichever pool still has work take the capacity the other left.
    if len(arxiv) + len(doi_only) < limit and len(arxiv) == half:
        arxiv = select("arxiv_id IS NOT NULL", "arxiv_id", limit - len(doi_only))
    return arxiv, doi_only


def mark_attempted(
    connection: psycopg.Connection[Any],
    *,
    paper_ids: list[UUID],
    now: datetime,
) -> None:
    if not paper_ids:
        return
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE papers SET
              metadata = metadata || %s,
              updated_at = now()
            WHERE id = ANY(%s);
            """,
            (Jsonb({"authors_attempted_at": now.isoformat()}), paper_ids),
        )


def count(authors: tuple[Author, ...], tally: Counter[str]) -> None:
    """Record what the providers actually carry, not what we hoped."""

    tally["authors"] += len(authors)
    tally["with_orcid"] += sum(1 for a in authors if a.orcid)
    tally["with_affiliation"] += sum(1 for a in authors if a.affiliation)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url", default=os.environ.get("CURIOUS_NOW_V2_DATABASE_URL")
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="papers to attempt per provider in this run (default 500)",
    )
    parser.add_argument(
        "--mailto",
        default=os.environ.get("CURIOUS_NOW_CONTACT_EMAIL"),
        help="contact address for Crossref's polite pool",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and report coverage without writing authors or marks",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.database_url:
        print("CURIOUS_NOW_V2_DATABASE_URL is not set", file=sys.stderr)
        return 2

    agent = USER_AGENT
    if args.mailto:
        agent = f"{USER_AGENT} (mailto:{args.mailto})"
    else:
        print(
            "warning: no --mailto or CURIOUS_NOW_CONTACT_EMAIL; "
            "Crossref will serve this from its anonymous pool",
            file=sys.stderr,
        )

    now = datetime.now(UTC)
    tally: Counter[str] = Counter()
    attempted: list[UUID] = []

    with psycopg.connect(args.database_url, autocommit=True) as connection:
        arxiv, doi_only = select_papers(connection, limit=args.limit)
        print(f"selected {len(arxiv)} arXiv and {len(doi_only)} DOI-only papers")

        by_arxiv = {value.casefold(): paper_id for paper_id, value in arxiv}
        with httpx.Client(timeout=httpx.Timeout(30)) as client:
            batches = arxiv_batches(tuple(value for _, value in arxiv))
            for index, batch in enumerate(batches):
                if index:
                    time.sleep(ARXIV_DELAY_SECONDS)
                try:
                    response = client.get(
                        ARXIV_API,
                        params={
                            "id_list": ",".join(batch),
                            "max_results": str(ARXIV_BATCH_SIZE),
                        },
                        headers={"User-Agent": agent},
                    )
                    response.raise_for_status()
                    found = parse_arxiv_authors(response.content)
                except Exception as exc:
                    tally["failed"] += len(batch)
                    print(f"  arxiv batch: {type(exc).__name__}: {exc}", file=sys.stderr)
                    continue
                for arxiv_id in batch:
                    paper_id = by_arxiv[arxiv_id.casefold()]
                    authors = found.get(arxiv_id.casefold(), ())
                    count(authors, tally)
                    tally["papers"] += 1
                    attempted.append(paper_id)
                    if authors and not args.dry_run:
                        store_authors(
                            connection,
                            paper_id=paper_id,
                            authors=authors,
                            source="arxiv_api",
                        )
                print(f"  arxiv {tally['papers']}/{len(arxiv)}")

            for position, (paper_id, doi) in enumerate(doi_only):
                if position:
                    time.sleep(CROSSREF_DELAY_SECONDS)
                try:
                    response = client.get(
                        f"{CROSSREF_API}/{doi}",
                        headers={"User-Agent": agent},
                        follow_redirects=True,
                    )
                    if response.status_code == httpx.codes.NOT_FOUND:
                        authors = ()
                    else:
                        response.raise_for_status()
                        authors = parse_crossref_authors(response.json())
                except Exception as exc:
                    tally["failed"] += 1
                    print(f"  {doi}: {type(exc).__name__}: {exc}", file=sys.stderr)
                    continue
                count(authors, tally)
                tally["papers"] += 1
                attempted.append(paper_id)
                if authors and not args.dry_run:
                    store_authors(
                        connection,
                        paper_id=paper_id,
                        authors=authors,
                        source="crossref_api",
                    )
                if position and position % 100 == 0:
                    print(f"  crossref {position}/{len(doi_only)}")

        if not args.dry_run:
            mark_attempted(connection, paper_ids=attempted, now=now)

    authors = tally["authors"]
    print(
        f"\n{'would store' if args.dry_run else 'stored'} {authors} authors "
        f"across {tally['papers']} papers; {tally['failed']} failed"
    )
    if authors:
        # The number that decides whether following a person needs OpenAlex.
        print(
            f"  ORCID on       {tally['with_orcid']:6d}  "
            f"({tally['with_orcid'] / authors:.0%})"
        )
        print(
            f"  affiliation on {tally['with_affiliation']:6d}  "
            f"({tally['with_affiliation'] / authors:.0%})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
